import clevercsv 
import json
import os
import math
import random
import string
import uuid
import pandas as pd
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from exceptions.exceptions import *
from utils.parser_weights_and_water import (
    get_water_control_mask, 
    get_estimated_weight_list,
    apply_noise
)
from data_manager.tables import * 
from utils.utils import sort_query, escape
from utils.dt_utils import * 
from flask import render_template

SACRIFICE_DATE = -1

class DManager:
    """! The data-manager class.

    Provides access to sql-database and handles getting and storing data to
    filesystem (pyrat(=animal) -data) and sql-database (experiment-data).

    @attribute protocols {"name": {"espaped":<str>, "subs":<Dict[str, str]>}
    """

    def __init__(self):
        """! The DManager class initializer. 

        @param sql_connector  sql-connector-class.
        """
        print(f"Initializing DManager...")
        self.mapping = {}
        self.keys_per_language = {}
        with open("resources/mapping.json") as f:
            mapping = json.load(f)
            for language, fields in mapping.items():
                self.mapping.update(fields)
                self.keys_per_language[language] = fields.keys()
        with open("resources/lines.json") as f:
            self.lines = json.load(f)

    def users(self) -> List[str]: 
        """! Gets list of all users (pyrat: 'Responsible') which are currently
        responsible for an animal.

        @return List of users.
        """
        animal_data = AnimalData.query.all()
        return [*set([data.user for data in animal_data])]  # converting to set removes dublicates 

    def protocols(self) -> Dict[str, str]:
        """! Gets list of all protocols which are currently
        applied for all animals (refers to pyrat data).

        @return List of protocols.
        """
        animal_data = AnimalData.query.all()
        return { 
            data.protocol:data.protocol_escaped for data in animal_data if data.protocol_escaped != "---"
        }

    def protocols_and_subprotocols(self) -> Dict[str, List[str]]: 
        """! Gets all protocols with list of their subprotocols. """
        protocols = {}
        for protocol in Protocol.query.all():
            protocols[protocol.name] = protocol.get_subprotocols()
        return protocols

    def extract_animal_data(self, file) -> Tuple[str, int]:
        """! Extracts and stores animal-data from csv file.

        @param tmp_path  Path for temporarily storing csv-file.
        @return status code: 409 if data for animal_id already exists 200 otherwise.
        """
        # Genrate temporary path
        tmp_path = "".join(random.choice(string.ascii_letters) for x in range(10))
        tmp_path += ".csv"
        # temporarily store file
        file.save(tmp_path)
        # Load file and delete tmp-file afterwards
        updated, total, mlas_with_date = self.__load_animal_data_from_csv(tmp_path)
        os.remove(tmp_path)
        # If none, send user information on which fields where missing.
        response = {"text":"", "animal_data": ""}
        if updated is None: 
            response["text"] = (f"CSV has missing keys, required: "
                + f"{' '.join(x for x in self.keys_per_language['en'])}"
                + f"or {' '.join(x for x in self.keys_per_language['en'])}")
            return response, 400
        # If success, update protocols (since new protocols might have been added)
        response["text"] = f"{total-len(updated)} inserted."
        if len(updated) > 0:
            response["text"] += f" {len(updated)} updated ({' '.join(x for x in updated)})"
        if len(mlas_with_date) > 0: 
            animal_data = []
            for mla, data in mlas_with_date.items(): 
                start, end = data
                animal_data.append(AnimalData.query.get(mla))
            response["animal_data"] = render_template(
                "overview_table_reduced.html", 
                animal_data=animal_data,
                mlas_with_date=mlas_with_date,
                protocols=self.protocols_and_subprotocols(),
            )
        return response, 200

    def set_protocol(
        self, animal_id: str, protocol: str, force: bool
    ) -> Tuple[str, int]:
        x, of = self.__is_stored(animal_id, ignore_death_date=True)
        if x > 0 and force is False: 
            return (
                f"{round((x/33)*100, 2)}% of data already filled. Sure you want proceed?", 
                409, 
                None
            )
        escaped_protocol = escape(protocol)
        animal_data = AnimalData.query.get(animal_id)
        animal_data.protocol = protocol
        animal_data.protocol_escaped = escaped_protocol
        animal_data.subprotocol = "---"
        self.__clear_experiment_data(animal_id)
        db.session.commit()
        return "", 200, escaped_protocol


    def set_subprotocol(
        self, animal_id: str, subprotocol: str, force: bool
    ) -> Tuple[str, int]:
        """! Updates subprotocol entry and initializes experiment-data.

        Uses the matching protocol and subprotocol to initialize the
        experiment-data with default values.

        @param animal_id  ID of animal.
        @param subprotocol  Subprotocol which to use for this animal.

        @return Tuple of error-message and http-return-code.
        """
        x, of = self.__is_stored(animal_id, ignore_death_date=True)
        if x > 0 and force is False: 
            return f"{round((x/33)*100, 2)}% of data already filled. Sure you want proceed?", 409
        print("Accessing animal_data: ", animal_id)
        animal_data = AnimalData.query.get(animal_id)
        animal_data.subprotocol = subprotocol
        if subprotocol == "---":
            self.__clear_experiment_data(animal_id)
            return "", 200
        full_protocol = f"{animal_data.protocol_escaped}/{subprotocol}"
        # Clear all existing data
        self.__clear_experiment_data(animal_id)
        # Initialize general 
        watercontrol = PWatercontrol.query.filter(PWatercontrol.protocol == full_protocol).first()
        default_general = PGeneral.query.filter(PGeneral.protocol == full_protocol).first()
        general = General(animal_id, full_protocol, watercontrol.allowed, default_general.suffering)
        db.session.add(general)
        # Initialize procedures:
        surgery_start = get_surgery_start(full_protocol)
        for protocol_procedure in PProcedure.query.filter(PProcedure.protocol == full_protocol): 
            procedure = Procedure.from_default(animal_id, animal_data.user, protocol_procedure)
            db.session.add(procedure)
        # Initialize medication and virus:
        def create_entry_from_template(Template, Table):
            for template in Template.query.filter(Template.protocol == full_protocol):
                entry = Table.from_default(animal_id, template)
                db.session.add(entry)
        create_entry_from_template(PMedication, Medication)
        create_entry_from_template(PVirus, Virus)
        db.session.commit()
        # If sacrifice-date already exists, set sacrifice-date for procedures referencing sacrifice-date
        fill_sacrifice_date(animal_id, full_protocol)
        return "", 200

    def set_death_date(self, animal_id, death_date):
        animal_data = AnimalData.query.get(animal_id)
        if animal_data: 
            animal_data.death_date = death_date
            db.session.commit()
            # Update medication/ procedures referencing sacrifice date (-1)
            if animal_data.protocol_escaped != "---" and animal_data.subprotocol != "---":
                full_protocol = f"{animal_data.protocol_escaped}/{animal_data.subprotocol}"
                fill_sacrifice_date(animal_id, full_protocol)
                # If experiment-data already exists, re-generate weights.
                general = General.query.get(animal_id)
                if general:
                    start_weight = general.start_weight if general.start_weight > 0 else -1
                    print(f"generating weights: {animal_id}, {start_weight}")
                    self.generate_weight_list(animal_id, start_weight)
                self.__update_stored(animal_id)
            return "", 200
        return f"AnimalData for {animal_id} not found", 404

    def update_experiment_data_entry(
        self, animal_id: str, category: str, data: Dict[str, any]
    ):
        Table = EXPERIMENT_TABLES[category] 
        element = Table.query.get(get_primary_key(category, animal_id, data))
        if element:
            element.update(data)
        else: 
            element = Table.from_form(animal_id, data)
            db.session.add(element)
        db.session.commit()
        # Update stored? of animal-data
        self.__update_stored(animal_id)

    def delete_animal_data(self, animal_id): 
        tables_to_delete = list(EXPERIMENT_TABLES.values())
        tables_to_delete.append(General)
        animal_data = AnimalData.query.get(animal_id)
        if animal_data:
            for Table in tables_to_delete: 
                rows = Table.query.filter(Table.animal_id == animal_id)
                if rows.first():
                    for row in rows:
                        db.session.delete(row)
            db.session.delete(animal_data)
            db.session.commit()
            return "", 200
        return "Animal not found", 404

    def delete_experiment_data_entry(
        self, animal_id: str, category: str, name: str, procedure: str = ""
    ):
        Table = EXPERIMENT_TABLES[category] 
        element = Table.query.get(
            get_primary_key(category, animal_id, {"name": name, "procedure": procedure})
        )
        if element:
            db.session.delete(element)
        db.session.commit()
    
    def get_experiment_data(self, animal_id: str) -> Dict[str, Dict[str, any]]:
        general = General.query.get(animal_id)
        protocol_general = PGeneral.query.get(general.experiment)
        experiment_data = {"general": table_to_json(general)}

        for name, Table in EXPERIMENT_TABLES.items(): 
            data = Table.query.filter(Table.animal_id == animal_id)
            experiment_data[name] = [table_to_json(t) for t in data]
        return experiment_data

    def get_surgery_sheet_data(self, animal_id: str) -> Dict[str, Dict[str, any]]:
        general = General.query.get(animal_id)
        protocol_general = PGeneral.query.get(general.experiment)
        data = {"general": table_to_json(general)}
    
        for name, Table in EXPERIMENT_TABLES_REDUCED.items(): 
            rows = Table.query.filter(Table.animal_id == animal_id)
            data[name] = [table_to_json(row) for row in rows]
        data["death_drugs"] = [
            x for x in data["medication"] if "sacrifice" in x["procedure"].lower()
        ]
        def get_entries_with_dates(table_name: str) -> List[Dict[str, any]]:
            entries_with_date = []
            for x in data[table_name]: 
                print(f"Searching procedure {x['procedure']} for {x['name']}")
                # Try Procedures
                procedures = Procedure.query.filter(
                    Procedure.animal_id == animal_id, Procedure.name == x["procedure"]
                ) 
                # Add entry for each found procedure
                for procedure in procedures:
                    for date in daterange_str(procedure.start_date, procedure.end_date):
                        x["date"] = date
                        entries_with_date.append(deepcopy(x))
            return entries_with_date
        data["medication"] = get_entries_with_dates("medication")
        data["viruses"] = get_entries_with_dates("viruses")
        print(data)
        return data
            

    def get_protocol_data(self, category: str, full_protocol: str): 
        # Get tables which should have only 1 element:
        if category not in PROTOCOL_TABLES:
            if category == "general":
                res = PGeneral.query.filter(PGeneral.protocol == full_protocol)
            if category == "watercontrol":
                res = PWatercontrol.query.filter(PWatercontrol.protocol == full_protocol)
            return table_to_json(res.first()) if res.first() else {}, {}
        # Get tables for all other categories.
        Table = PROTOCOL_TABLES[category]
        protocol_data = Table.query.filter(Table.protocol == full_protocol)
        # Sort tables by days_after_start:
        if category == "procedures":
            protocol_data = sort_query(protocol_data, "days_after_start")
        # Get definitions:
        if category == "allowed_animals":
            definitions = self.lines
        else:
            definitions = sort_query(DEFINITION_TABLES[category].query.all(), "name")
        return protocol_data, definitions

    def get_p9_data(self, escaped_protocol: str): 
        protocol = Protocol.query.get(escaped_protocol)
        subprotocols = {}
        def to_string(elems, procedure): 
            return ", ".join([e.string() for e in elems if e.date in dates])

        def procedures(procedures, medication, viruses):
            procedures = sort_query(procedures, "start_date")
            data = {}
            for p in procedures: 
                # Skip if date not yet filled.
                if not date_filled(p.start_date) or not date_filled(p.end_date):
                    continue
                default = get_protocol_entry_by_name(PProcedure, general.experiment, p.name)
                if (p.start_date, p.end_date) not in data: 
                    data[(p.start_date, p.end_date)] = {
                        "start": convert(p.start_date), 
                        "end": convert(p.end_date), 
                        "names": p.name, 
                        "medication": "", 
                        "viruses": "", 
                    }
                else: 
                    data[(p.start_date, p.end_date)]["names"] += f", {p.name}"

                meds = ", ".join([m.string() for m in medication if m.procedure == p.name])
                virs = ", ".join([v.string() for v in viruses if v.procedure == p.name])
                data[(p.start_date, p.end_date)]["medication"] += meds
                data[(p.start_date, p.end_date)]["viruses"] += virs
            return list(data.values())

        for sub in protocol.get_subprotocols():
            full_protocol = f"{escaped_protocol}/{sub}"
            generals = General.query.filter(General.experiment == full_protocol)
            data = {"animals": [], "experiment": sub}
            if generals.first():
                data["subprotocol"] = PGeneral.query.get(generals.first().experiment)
                for general in generals:
                    animal_data = AnimalData.query.get(general.animal_id)
                    # Get all procedures with matching medication:
                    all_procedures = procedures(
                        Procedure.query.filter(Procedure.animal_id == animal_data.mla_num),
                        Medication.query.filter(Medication.animal_id == animal_data.mla_num),
                        Virus.query.filter(Virus.animal_id == animal_data.mla_num),
                    )
                    # Skip if start-date is not yet set or procedures are empty.
                    if not date_filled(general.start) or len(all_procedures) == 0:
                        continue
                    # Use "???" if animal's date of death is not yet set.
                    if date_filled(animal_data.death_date):
                        end_date = convert(animal_data.death_date) 
                    else:
                        end_date = "???"
                    data["animals"].append({
                        "general": general, 
                        "animal_data": animal_data, 
                        "procedures": all_procedures,
                        "start": convert(general.start),
                        "end": end_date
                    })
                subprotocols[full_protocol] = data
            else: 
                print("No data for this subprotocol")
        return subprotocols, protocol.name

    def update_dates(
        self, animal_id: str, start_date_str: str, autofill: bool
    ) -> Tuple[str, int]:
        """! Updates dates of experiment-data according to protocol-data. 

        @param animal_id  ID of animal 
        @param start_date_str  Start date based on which dates are filled. 

        @return Tuple of error-message and http-return-code.
        """
        start_date = strtodate(start_date_str)
        # Update start-date in General
        general = General.query.get(animal_id)
        old_start_date = general.start
        general.start = datetostr(start_date, SOURCE_DATE_FORMAT)
        if autofill is False: 
            db.session.commit()
            return "Start date updated without updating other dates.", 200
        general = General.query.get(animal_id)
        surgery_start = get_surgery_start(general.experiment)
        not_updated = []
        def get_date(inc):
            return datetostr(incdate(start_date, inc), SOURCE_DATE_FORMAT)
        # Update procedures: 
        for x in Procedure.query.filter(Procedure.animal_id == animal_id): 
            default = PProcedure.query.get(x.protocol_entry_uuid)
            x.start_date = get_date(int(default.days_after_start))
            x.end_date = get_date(int(default.days_after_start)+int(default.duration)-1)
        db.session.commit()
        fill_sacrifice_date(animal_id, general.experiment)
        self.__update_stored(animal_id)
        if not date_filled(old_start_date):
            self.generate_weight_list(animal_id, -1)
        return f"Dates where updated. Make sure to doublecheck! {len(not_updated)} dates where not updated: {json.dumps(not_updated)} ", 200

    def update_weights_and_watercontrol(
        self, animal_id: str, weights: str, water_control_mask: str
    ) -> Tuple[str, int]:
        """! Updates a field of in an animal entry. """
        general = General.query.get(animal_id)
        general.watercontrol_mask = water_control_mask
        general.weights = weights
        general.set_start_weight(json.loads(weights)[0])
        db.session.commit()
        self.__update_stored(animal_id)
        return "success", 200

    def update_definitions_entry(self, category: str, data: Dict[str, any]):
        """! Updates or creates new definition entry. """
        Table = DEFINITION_TABLES[category] 
        definitions_entry = Table.query.get(data["name"])
        if definitions_entry:
            definitions_entry.update(data)
        else: 
            definitions_entry = Table.from_json(data)
            db.session.add(definitions_entry)
        db.session.commit()

    def update_protocol_entry(self, category: str, protocol: str, data: Dict[str, any]):
        """! Updates or creates new definition entry. """
        # Get protocol-entry from table definied by category
        if category == "general": 
            protocol_entry = PGeneral.query.get(data["uuid"]) 
            Table = PGeneral
        elif category == "watercontrol": 
            protocol_entry = PWatercontrol.query.get(data["uuid"]) 
            Table = PWatercontrol
        else: 
            Table = PROTOCOL_TABLES[category] 
            protocol_entry = Table.query.get(data["uuid"]) 
        # Update or add new protocol entry depending on wether it existed before.
        if protocol_entry:
            protocol_entry.update(data)
        else: 
            # Make sure element does not already exist.
            if category != "general" and category != "watercontrol":
                if category == "medication":
                    query = Table.query.filter(
                        Table.protocol==protocol, Table.name==data["name"], Table.procedure==data["procedure"]
                    )
                elif category == "procedures":
                    query = Table.query.filter(
                        Table.protocol==protocol, 
                        Table.name==data["name"], 
                        Table.days_after_start==data["days_after_start"]
                    )
                else:
                    query = Table.query.filter(Table.protocol==protocol, Table.name==data["name"])
                if query.first():
                    raise DublicateEntry("A entry with the same name already exists!")
            protocol_entry = Table.from_form(str(uuid.uuid4()), protocol, data)
            db.session.add(protocol_entry)
        db.session.commit()

    def delete_protocol_entry(self, category: str, uuid: str):
        Table = PROTOCOL_TABLES[category] 
        protocol_entry = Table.query.get(uuid)
        if protocol_entry:
            db.session.delete(protocol_entry)
        db.session.commit()

    def delete_definitions_entry(self, category: str, name: str):
        Table = DEFINITION_TABLES[category] 
        definition_entry = Table.query.get(name)
        if definition_entry:
            db.session.delete(definition_entry)
        db.session.commit()

    def store_note(self, animal_id: str, category: str, text: str) -> bool: 
        """! Stores a given note under animal_id and category in database. 

        @param animal_id  ID of animal 
        @param category  Category (like general, procedures, ...)
        @param note  The actual note
        @return Boolean indicating success/ failure.
        """
        note = Note.query.get((animal_id, category))
        if note:
            note.note = text
        else:
            note = Note(animal_id, category, text) 
            db.session.add(note)
        db.session.commit()
        return True

    def generate_weight_list(self, animal_id: str, start_weight: int) -> Tuple[str, int]:
        # Update start weight:
        general = General.query.get(animal_id)
        general.set_start_weight(start_weight)
        db.session.commit()
        general = General.query.get(animal_id)

        # Get animal data and watercontrol infos:
        animal_data = AnimalData.query.get(animal_id)
        start_date = general.start
        if not date_filled(start_date): 
            return "Missing start-date", 401
        watercontrol_infos = PWatercontrol.query.filter(PWatercontrol.protocol == general.experiment).first()

        # Get some values 
        start_weight = float(start_weight) if start_weight != "" else -1
        sacrifice_date = today()
        if date_filled(animal_data.death_date): 
            sacrifice_date = strtodate(animal_data.death_date)
        start_date = strtodate(start_date) 
        dob = strtodate(animal_data.dob)
        age_at_start = (start_date - dob).days
        duration = len(daterange(start_date, sacrifice_date))-1

        # Generate water-control-mask, if watercontrol is allowed:
        if watercontrol_infos.allowed:
            days_after_start = int(watercontrol_infos.days_after_start)
            water_restriction_start = incdate(start_date, days_after_start)
            surgery_dates = get_surgery_dates(animal_id, general.experiment)
            duration_water = len(daterange(water_restriction_start, sacrifice_date))
            if duration_water > int(watercontrol_infos.duration):
                duration_water = int(watercontrol_infos.duration)
            if duration_water > duration:
                duration_water = duration
            # Calculate water-control-mask and estimated weights
            water_control_mask = get_water_control_mask(
                water_restriction_start, duration_water, surgery_dates, sacrificed=True
            )
            # Add `False`-values for days_after_start  
            water_control_mask = [False for _ in range(days_after_start)] + water_control_mask
            water_control_mask = water_control_mask + [
                False for _ in range(duration-(len(water_control_mask)-1))
            ]
        else:
            water_control_mask = [False for _ in range(duration+1)]
        # Generate estimated weights 
        estimated_weights = get_estimated_weight_list(
            age_at_start, animal_data.sex, duration, water_control_mask, start_weight
        )
        weights = apply_noise(estimated_weights, 0.070, start_weight==-1)

        # Update general data:
        general.watercontrol_mask = json.dumps(water_control_mask)
        general.weights = json.dumps(weights)
        general.set_start_weight(round(estimated_weights[0], 2))
        db.session.commit()
        return "success", 200

    def __clear_experiment_data(self, animal_id: str) -> int:
        """! Clears experiment-data for animal

        @param animal_id  ID of animal

        @return status code: 200 on success.
        """
        def delete(table):
            for x in table.query.filter(table.animal_id == animal_id):
                db.session.delete(x)
        for x in [General, Medication, Procedure, Virus]:
            delete(x)
        db.session.commit()
        self.__update_stored(animal_id)
        return 200

    def __load_animal_data_from_csv(self, path: str):
        """! Loads animal-data from CSV file.

        @param path  Path to CSV. 
        @return List of animal-ids which where updated, and total number of
            animal-ids in dataframe.
        """
        # Checks whether all neccesarry keys are included.
        def check_all_keys(df: pd.DataFrame) -> bool: 
            for language_keys in self.keys_per_language.values():
                if all(key in df.keys() for key in language_keys):
                    return True
            return False
        # Load csv
        df = clevercsv.read_dataframe(path)
        if check_all_keys(df) == False: 
            return None, None, None
        # Iterate over keys and add to data using mapping.
        updated = []
        mlas_with_date = {}
        for _, row in df.iterrows():
            data = {}
            start = ""
            end = ""
            for key in df.keys():
                value = row[key]
                if key in self.mapping:
                    data[self.mapping[key]] = str(value)
                    if self.mapping[key] == "protocol_pyrat":
                        for protocol in Protocol.query.all():
                            if str(value) in protocol.name:
                                data["protocol"] = protocol.name
                                data["protocol_escaped"] = escape(str(protocol.name))
                    if self.mapping[key] == "comment":
                        start, end = self.__get_start_end_from_comment(value)
            # Create or update animal-data
            animal_id = data["id"]
            mlas_with_date[animal_id] = {"start":start, "end":end}
            animal_data = AnimalData.query.get(animal_id)
            if animal_data:
                animal_data.update(data)
                updated.append(animal_id)
            else: 
                animal_data = AnimalData(data)
                db.session.add(animal_data)
            db.session.commit()
            fill_sacrifice_date(
                animal_id, f"{animal_data.protocol_escaped}/{animal_data.subprotocol}"
            )
            self.__update_stored(animal_id)
        return updated, len(df), mlas_with_date


    def __is_stored(self, animal_id: str, ignore_death_date: bool = False) -> bool:
        """! Checks if experiment-data is stored. 

        Checks if animal is dead (`death_date` is filled) and whether
        all experiment-steps are done (assuming that everything is done when
        `start` and `end` or filled)

        @param animal_id  ID of animal.
        @param ignore_death_date If True does not concider death date
        @return Boolean indicating whether data is stored or not.
        """
        dates_counter = [0, 2 if not ignore_death_date else 1] # start (and death_date)
        general = General.query.get(animal_id)
        if general is None: 
            return 0, 100
        dates_counter[0] += 1 if date_filled(general.start) else 0
        animal_data = AnimalData.query.get(animal_id)
        if not ignore_death_date:
            dates_counter[0] += 1 if date_filled(animal_data.death_date) else 0
        # Check procedures for dates
        for entry in Procedure.query.filter(Procedure.animal_id == animal_id):
            dates_counter[0] += 1 if date_filled(entry.start_date) else 0
            dates_counter[0] += 1 if date_filled(entry.end_date) else 0
            dates_counter[1] += 2 
        return dates_counter[0], dates_counter[1]

    def __update_stored(self, animal_id): 
        x, of = self.__is_stored(animal_id)
        animal_data = AnimalData.query.get(animal_id) 
        if x == of:
            animal_data.stored = True
        else: 
            animal_data.stored = False
        db.session.commit()

    def __get_start_end_from_comment(self, value): 
        def extract(name: str, parts: List[str]):
            for part in parts: 
                if name in part: 
                    date = part[part.find(":")+1:].strip()
                    return convert_source_2_to_1(date)
            return None
        parts = value.split(";")
        return extract("start", parts), extract("end", parts)

def get_surgery_start(protocol: str):
    procedures = PProcedure.query.filter(PProcedure.protocol == protocol)
    surgery_start = 900
    for procedure in procedures: 
        if procedure.surgery and int(procedure.days_after_start) < surgery_start:
            surgery_start = int(procedure.days_after_start)
    return surgery_start


def get_primary_key(category: str, animal_id: str, data: Dict[str, any]): 
    if category == "medication":
        return (animal_id, data["name"], data["procedure"]) 
    return (animal_id, data["name"]) 


def get_surgery_dates(animal_id: str, protocol: str): 
    procedures = Procedure.query.filter(Procedure.animal_id == animal_id)
    surgery_dates = []
    for procedure in procedures:
        # Get matching protocol-entry to check if procedure is a surgery
        protocol_procedure = get_protocol_entry_by_name(PProcedure, protocol, procedure.name)
        if protocol_procedure.surgery:
            for date in daterange(strtodate(procedure.start_date), strtodate(procedure.end_date)):
                surgery_dates.append(date)
    return surgery_dates

def fill_sacrifice_date(animal_id: str, protocol: str):
    animal_data = AnimalData.query.get(animal_id)
    if not date_filled(animal_data.death_date):
        return
    entries = Procedure.query.filter(Procedure.animal_id == animal_id) 
    if entries.first():
        for entry in entries: 
            template = PProcedure.query.get(entry.protocol_entry_uuid)
            if not template: 
                continue
            if template and template.days_after_start == str(SACRIFICE_DATE):
                entry.set_date(animal_data.death_date)
    db.session.commit()


def get_protocol_entry_by_uuid(Table, uuid: str):
    entry = Table.query.get(uuid)
    if not entry:
        raise EntryNotFound(f"For table {Table} with uuid {uuid}: no entry found!", 404)
    return entry

def get_protocol_entry_by_name(Table, protocol: str, name: str):
    res = Table.query.filter(Table.protocol == protocol, Table.name == name)
    if not res.first(): 
        raise QueryEmpty(
            f"For table {Table} with protocol {protocol} and name {name}: no entry found!", 404
        )
    return res.first() 
