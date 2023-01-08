import clevercsv 
import json
import os
import math
import random
import string
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from data_manager.sql_connector import SqlConnector
from exceptions.exceptions import ParserException
from utils.parser_weights_and_water import (
    get_water_control_mask, 
    get_estimated_weight_list,
    apply_noise
)
from data_manager.tables import (
    AMedication, AProcedure, AVirus,
    PGeneral, PAnesthesia, PAnalgesia, PProcedure, PVirus, PWatercontrol,
    General, Anesthesia, Analgesia, Procedure, PostProcedure, Virus,
    Protocol, 
    db, table_to_json, EXPERIMENT_TABLES, PROTOCOL_TABLES, DEFINITION_TABLES
)
from utils.utils import sort
from utils.dt_utils import strtodate, datetostr, incdate, daterange, SOURCE_DATE_FORMAT

# Main tables
T_ANIMAL_DATA = "animal_data"
T_NOTES = "notes"

class DManager:
    """! The data-manager class.

    Provides access to sql-database and handles getting and storing data to
    filesystem (pyrat(=animal) -data) and sql-database (experiment-data).

    @attribute protocols {"name": {"espaped":<str>, "subs":<Dict[str, str]>}
    """

    def __init__(self, sql_connector: SqlConnector):
        """! The DManager class initializer. 

        @param sql_connector  sql-connector-class.
        """
        print(f"Initializing DManager...")
        self.sql = sql_connector
        self.mapping = {}
        self.keys_per_language = {}
        with open("resources/mapping.json") as f:
            mapping = json.load(f)
            for language, fields in mapping.items():
                self.mapping.update(fields)
                self.keys_per_language[language] = fields.keys()

    def users(self) -> List[str]: 
        """! Gets list of all users (pyrat: 'Responsible') which are currently
        responsible for an animal.

        @return List of users.
        """
        return self.sql.get_all(T_ANIMAL_DATA, "user")

    def protocols(self) -> Dict[str, str]:
        """! Gets list of all protocols which are currently
        applied for all animals (refers to pyrat data).

        @return List of protocols.
        """
        protocols = self.sql.get_all(T_ANIMAL_DATA, "protocol")
        return { p:escape_protocol(p) for p in protocols }

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
        updated, total = self.__load_animal_data_from_csv(tmp_path)
        os.remove(tmp_path)
        # If none, send user information on which fields where missing.
        if updated is None: 
            return (f"CSV has missing keys, required: "
                + f"{' '.join(x for x in self.keys['en'])}"
                + f"or {' '.join(x for x in self.keys['en'])}")
        # If success, update protocols (since new protocols might have been added)
        inserted_msg =f"{total-len(updated)} inserted."
        if len(updated) == 0:
            return inserted_msg, 200
        updated_msg = f"{len(updated)} updated ({' '.join(x for x in updated)})"
        return inserted_msg + " " + updated_msg, 206 

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
        res = self.sql.update(T_ANIMAL_DATA, {"id":animal_id}, {"subprotocol":subprotocol})
        if subprotocol == "---":
            return "", 200
        if res is None:
            return "An error occured, when setting subprotocol", 500
        animal_data = self.__get_animal_entry(animal_id)
        full_protocol = f"{animal_data['protocol_escaped']}/{subprotocol}"
        # Clear all existing data
        self.__clear_experiment_data(animal_id)
        # Initialize general 
        watercontrol = PWatercontrol.query.get(full_protocol)
        general = General(animal_id, full_protocol, watercontrol.allowed)
        db.session.add(general)
        # Initialize procedures:
        surgery_start = get_surgery_start(full_protocol)
        for protocol_procedure in PProcedure.query.filter(PProcedure.protocol == full_protocol): 
            if int(protocol_procedure.days_after_start) > surgery_start: 
                procedure = PostProcedure.from_default(
                    animal_id, animal_data["user"], protocol_procedure
                )
            else: 
                procedure = Procedure.from_default(
                    animal_id, animal_data["user"], protocol_procedure
                )
            db.session.add(procedure)
        # Initialize medication:
        for protocol_anesthesia in PAnesthesia.query.filter(PAnesthesia.protocol == full_protocol):
            for x in range(int(protocol_anesthesia.days_after_surgery)+1):
                anesthetic = Anesthesia.from_default(animal_id, protocol_anesthesia, x)
                db.session.add(anesthetic)
        for protocol_analgesia in PAnalgesia.query.filter(PAnalgesia.protocol == full_protocol):
            for x in range(int(protocol_analgesia.days_after_surgery)+1):
                analgesia = Analgesia.from_default(animal_id, protocol_analgesia, x)
                db.session.add(analgesia)
        # Initialize viruses:
        for protocol_virus in PVirus.query.filter(PVirus.protocol == full_protocol):
            virus = Virus.from_default(animal_id, protocol_virus)
            db.session.add(virus)
        db.session.commit()
        return "", 200

    def update_experiment_data_entry(
        self, animal_id: str, category: str, data: Dict[str, any]
    ):
        Table = EXPERIMENT_TABLES[category] 
        element = Table.query.get(get_primary_key(category, animal_id, data))
        if element:
            element.update(data)
        else: 
            element = Table.from_json(animal_id, data)
            db.session.add(element)
        db.session.commit()

    def delete_experiment_data_entry(
        self, animal_id: str, category: str, name: str, date: str = ""
    ):
        Table = EXPERIMENT_TABLES[category] 
        element = Table.query.get(
            get_primary_key(category, animal_id, {"name": name, "date": date})
        )
        if element:
            db.session.delete(element)
        db.session.commit()
    
    def get_experiment_data(self, animal_id: str) -> Dict[str, Dict[str, any]]:
        general = General.query.get(animal_id)
        protocol_general = PGeneral.query.get(general.experiment)
        medication_infos = AMedication.query.get(protocol_general.death_drug)
        experiment_data = {"general": table_to_json(general)}
        experiment_data["general"]["death_drug"] = protocol_general.death_drug
        experiment_data["general"]["death_drug_amount"] = medication_infos.amount
        experiment_data["general"]["death_drug_concentration"] = medication_infos.concentration

        print("death_drug: ", protocol_general.death_drug)
        print("General: ", experiment_data["general"])
        for name, Table in EXPERIMENT_TABLES.items(): 
            data = Table.query.filter(Table.animal_id == animal_id)
            experiment_data[name] = [table_to_json(t) for t in data]
        return experiment_data

    def get_protocol_data(self, category: str, full_protocol: str): 
        print("Got category: ", category)
        if category == "general":
            general = PGeneral.query.get(full_protocol)
            data = table_to_json(general) if general else {}
            return data, AMedication.query.all()

        if category == "watercontrol":
            watercontrol = PWatercontrol.query.get(full_protocol)
            data = table_to_json(watercontrol) if watercontrol else {}
            return data, {}
        Table = PROTOCOL_TABLES[category]
        protocol_data = Table.query.filter(Table.protocol == full_protocol)
        definition_category = category if category not in ["anesthesia", "analgesia"] else "medication"
        DefinitionsTable = DEFINITION_TABLES[definition_category]
        definitions = DefinitionsTable.query.all()
        return protocol_data, definitions

    def update_dates(self, animal_id: str, start_date: str, autofill: bool) -> Tuple[str, int]:
        """! Updates dates of experiment-data according to protocol-data. 

        @param animal_id  ID of animal 
        @param start_date  Start date based on which dates are filled. 

        @return Tuple of error-message and http-return-code.
        """
        start_date = strtodate(start_date)
        # Update start-date in General
        general = General.query.get(animal_id)
        general.start = datetostr(start_date, SOURCE_DATE_FORMAT)
        db.session.commit()
        if autofill is False: 
            return "Start date updated without updating other dates.", 200
        general = General.query.get(animal_id)
        surgery_start = get_surgery_start(general.experiment)
        not_updated = []
        def get_date(inc):
            return datetostr(incdate(start_date, inc), SOURCE_DATE_FORMAT)
        # Update medication:
        def update_medication(table): 
            for x in table.query.filter(table.animal_id == animal_id): 
                if not x.days_after_surgery == -1:
                    x.date = get_date(x.days_after_surgery+surgery_start)
                else: 
                    not_updated.append((x.name, x.date))
        update_medication(Anesthesia)
        update_medication(Analgesia)  
        # Update procedures: 
        def update_procedure(table): 
            for x in table.query.filter(table.animal_id == animal_id): 
                default = PProcedure.query.get((general.experiment, x.name))
                x.start_date = get_date(int(default.days_after_start))
                x.end_date = get_date(int(default.days_after_start)+int(default.duration))
        update_procedure(Procedure) 
        update_procedure(PostProcedure) 
        # Update viruses:
        for x in Virus.query.filter(Virus.animal_id == animal_id): 
            default_entry = PVirus.query.get((general.experiment, x.name))
            x.date = get_date(int(default_entry.days_after_start))
        db.session.commit()
        return f"Dates where updated. Make sure to doublecheck! {len(not_updated)} dates where not updated: {json.dumps(not_updated)} ", 200

    def update_weights_and_watercontrol(
        self, animal_id: str, weights: str, water_control_mask: str
    ) -> Tuple[str, int]:
        """! Updates a field of in an animal entry. """
        general = General.query.get(animal_id)
        general.watercontrol_mask = water_control_mask
        general.weights = weights
        general.start_weight = json.loads(weights)[0]
        db.session.commit()
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
        print("Got data: ", data)
        if category == "general": 
            protocol_entry = PGeneral.query.get(protocol) 
            Table = PGeneral
        elif category == "watercontrol": 
            protocol_entry = PWatercontrol.query.get(protocol) 
            Table = PWatercontrol
        else: 
            Table = PROTOCOL_TABLES[category] 
            protocol_entry = Table.query.get((protocol, data["name"])) 
        # Update or add new protocol entry depending on wether it existed before.
        if protocol_entry:
            protocol_entry.update(data)
        else: 
            protocol_entry = Table.from_json(protocol, data)
            db.session.add(protocol_entry)
        db.session.commit()

    def delete_protocol_entry(
        self, category: str, protocol: str, name: str
    ):
        Table = PROTOCOL_TABLES[category] 
        protocol_entry = Table.query.get((protocol, name))
        if protocol_entry:
            db.session.delete(protocol_entry)
        db.session.commit()

    def delete_definitions_entry(self, category: str, name: str):
        Table = DEFINITION_TABLES[category] 
        definition_entry = Table.query.get(name)
        if definition_entry:
            db.session.delete(definition_entry)
        db.session.commit()

    def store_note(self, animal_id: str, category: str, note: str) -> bool: 
        """! Stores a given note under animal_id and category in database. 

        @param animal_id  ID of animal 
        @param category  Category (like general, procedures, ...)
        @param note  The actual note
        @return Boolean indicating success/ failure.
        """
        joined_id = animal_id + "/" + category
        if len(self.sql.get(T_NOTES, joined_id, "id")) == 0: 
            data = {"id": joined_id, "animal_id": animal_id, "category": category, "note": note}
            self.sql.insert(T_NOTES, [data])
        else:
            self.sql.update(T_NOTES, {"id": joined_id}, {"note": note})
        return True

    def get_notes(self, animal_id): 
        notes = self.sql.get(T_NOTES, animal_id)
        return { note["category"]:note["note"] for note in notes }

    def get_animal_data(self, filter_tag: str=None, key: str=None) -> List[Dict[str, any]]:
        """! Gets animal-data with possibility to filter by keys.

        @param filter_tag  tag by which to filter.
        @param key  key to match filter tag.

        @return list of animal data.
        """
        # Get animal data based on filter_tag and key
        animal_data = self.sql.get(T_ANIMAL_DATA, key, filter_tag)
        # Add stored? information
        for data in animal_data:
            x, of = self.__is_stored(data["id"])
            data["stored"] = x == of
        return animal_data

    def generate_weight_list(self, animal_id: str, start_weight: int) -> Tuple[str, int]:
        # Update start weight:
        general = General.query.get(animal_id)
        general.start_weight = start_weight
        db.session.commit()
        general = General.query.get(animal_id)

        # Get animal data and watercontrol infos:
        animal_data = self.__get_animal_entry(animal_id)
        if not date_filled(animal_data["death_date"]): 
            return "Animal is not yet sacrificed", 200
        start_date = general.start
        if not date_filled(start_date): 
            return "Missing start-date", 401
        watercontrol_infos = PWatercontrol.query.get(general.experiment)

        # Get some values 
        start_weight = float(start_weight) if start_weight != "" else -1
        sacrifice_date = strtodate(animal_data["death_date"])
        start_date = strtodate(start_date) 
        dob = strtodate(animal_data["dob"])
        age_at_start = (start_date - dob).days
        duration = len(daterange(start_date, sacrifice_date))

        # Generate water-control-mask, if watercontrol is allowed:
        if watercontrol_infos.allowed:
            days_after_start = int(watercontrol_infos.days_after_start)
            water_restriction_start = incdate(start_date, days_after_start)
            surgery_dates = get_surgery_dates(animal_id, general.experiment)
            duration_water = len(daterange(water_restriction_start, sacrifice_date)) # TODO concider duration
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
            age_at_start, animal_data["sex"], duration, water_control_mask, start_weight
        )
        weights = apply_noise(estimated_weights, 0.070, start_weight==-1);

        # Update general data:
        general.watercontrol_mask = json.dumps(water_control_mask)
        general.weights = json.dumps(weights)
        general.start_weight = round(estimated_weights[0], 2)
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
        for x in [General, Anesthesia, Analgesia, Procedure, PostProcedure, Virus]:
            delete(x)
        db.session.commit()
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
            return None, None
        # Iterate over keys and add to data using mapping.
        updated = []
        for _, row in df.iterrows():
            data = {}
            for key in df.keys():
                value = row[key]
                if key in self.mapping:
                    data[self.mapping[key]] = value
                    if self.mapping[key] == "protocol":
                        data["protocol_escaped"] = escape_protocol(value)
            # If not already exists, include "empty" subprotocol and insert to sql.
            if len(self.sql.get(T_ANIMAL_DATA, data["id"], "id")) == 0:
                data["subprotocol"] = "---"
                self.sql.insert(T_ANIMAL_DATA, [data])
            # Otherwise, update data.
            else: 
                self.sql.update(T_ANIMAL_DATA, {"id":data["id"]}, data)
                updated.append(data["id"])
        return updated, len(df)


    def __get_animal_entry(self, animal_id: str) -> Dict[str, any]:
        """! Gets single entry from animal-data matching given ID.

        @param animal_id  ID of animal to search for.
        @return Entry for given ID or `None` if ID was not found.
        """
        animal_data = self.sql.get(T_ANIMAL_DATA, animal_id, "id")
        if len(animal_data) > 0:
            return animal_data[0]
        return None

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
        animal_data = self.__get_animal_entry(animal_id)
        if not ignore_death_date:
            dates_counter[0] += 1 if date_filled(animal_data["death_date"]) else 0
        for Table in [Anesthesia, Analgesia, Virus]: 
            for entry in Table.query.filter(Table.animal_id == animal_id):
                dates_counter[0] += 1 if date_filled(entry.date) else 0
                dates_counter[1] += 1
        for Table in [Procedure, PostProcedure]: 
            for entry in Table.query.filter(Table.animal_id == animal_id):
                dates_counter[0] += 1 if date_filled(entry.start_date) else 0
                dates_counter[0] += 1 if date_filled(entry.end_date) else 0
                dates_counter[1] += 2 
        return dates_counter[0], dates_counter[1]

def date_filled(date_str: str) -> bool: 
    return len(date_str) == 10


def escape_protocol(protocol: str) -> str: 
    """! Escape protocol-string to be url compatible. 

    Removes whitespaces (" ") and replaces slashs ("/") underscore ("_").
    
    @param protocol  Protocol-name.
    @return Escaped protocol-name.
    """
    return protocol.replace(" ", "").replace("/", "_")


def get_surgery_start(protocol: str):
    procedures = PProcedure.query.filter(PProcedure.protocol == protocol)
    surgery_start = 900
    for procedure in procedures: 
        if procedure.surgery and int(procedure.days_after_start) < surgery_start:
            surgery_start = int(procedure.days_after_start)
    return surgery_start


def get_primary_key(category: str, animal_id: str, data: Dict[str, any]): 
    if category == "analgesia" or category == "anesthesia":
        return (animal_id, data["name"], data["date"]) 
    return (animal_id, data["name"]) 


def get_surgery_dates(animal_id: str, protocol: str): 
    procedures = Procedure.query.filter(Procedure.animal_id == animal_id)
    surgery_dates = []
    for procedure in procedures:
        # Get matching protocol-entry to check if procedure is a surgery
        protocol_procedure = PProcedure.query.get((protocol, procedure.name))
        if protocol_procedure.surgery:
            for date in daterange(strtodate(procedure.start_date), strtodate(procedure.end_date)):
                surgery_dates.append(date)
    return surgery_dates
