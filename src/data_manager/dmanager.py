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
    PAnesthesia, PAnalgesia, PProcedure, PVirus, PWatercontrol,
    General, Anesthesia, Analgesia, Procedure, PostProcedure, Virus,
    Protocol, 
    db,
    table_to_json
)
from utils.utils import sort
from utils.dt_utils import strtodate, datetostr, incdate, daterange, SOURCE_DATE_FORMAT

ANESTHETIC = ["Ketamine / Xylazine", "Isoflurane"]
# Some important keys
DAYS_AFTER_START = "days_after_start"
DAYS_AFTER_SURGERY = "days_after_surgery"
DURATION_IN_DAYS = "duration_in_days"
# Main tables
T_ANIMAL_DATA = "animal_data"
T_NOTES = "notes"

SOURCE_DATE_FORMAT = "%Y-%m-%d"
OUTPUT_DATE_FORMAT = "%d.%m.%y"

@dataclass
class ExperimentData: 
    """! The experiment-data DTO class."""
    stored: bool
    general: Dict[str, any]
    viruses: Dict[str, any]
    anesthetic: List[Dict[str, any]]
    analgesic: List[Dict[str, any]]
    procedures: List[Dict[str, any]]
    post_procedures: List[Dict[str, any]]
    surgery_start: int 
    availible_anesthetic: List[str] = field(default_factory=list)
    availible_analgesic: List[str] = field(default_factory=list)
    availible_viruses: List[str] = field(default_factory=list)

    def __post_init__(self):
        """! Generates availible anesthetic/ anesthetic from given data. """
        self.availible_anesthetic = [x["name"] for x in self.anesthetic]
        self.availible_analgesic = [x["name"] for x in self.analgesic]
        self.availible_viruses = [x["name"] for x in self.viruses]

    def set_general(self, general: List[Dict[str, any]]):
        self.general = general

    def dict(self):
        return {
            "general": self.general, 
            "anesthetic":self.anesthetic,
            "analgesic":self.analgesic,
            "procedures":self.procedures,
            "post_procedures":self.post_procedures
        }


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

    def protocols(self) -> List[str]:
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

    def set_subprotocol(self, animal_id: str, subprotocol: str) -> Tuple[str, int]:
        """! Updates subprotocol entry and initializes experiment-data.

        Uses the matching protocol and subprotocol to initialize the
        experiment-data with default values.

        @param animal_id  ID of animal.
        @param subprotocol  Subprotocol which to use for this animal.

        @return Tuple of error-message and http-return-code.
        """
        res = self.sql.update(T_ANIMAL_DATA, {"id":animal_id}, {"subprotocol":subprotocol})
        if res is None:
            return "An error occured, when setting subprotocol", 500
        animal_data = self.__get_animal_entry(animal_id)
        full_protocol = f"{animal_data['protocol_escaped']}/{subprotocol}"
        # Clear all existing data
        self.__clear_experiment_data(animal_id)
        # Initialize general 
        general = General(animal_id, full_protocol, True)  # TODO Get corret watercontrol
        db.session.add(general)
        # Initialize procedures
        surgery_start = get_surgery_start(full_protocol)
        for protocol_procedure in PProcedure.query.filter(PProcedure.protocol == full_protocol): 
            if int(protocol_procedure.days_after_start) > surgery_start: 
                procedure = PostProcedure(animal_id, animal_data["user"], protocol_procedure)
            else: 
                procedure = Procedure(animal_id, animal_data["user"], protocol_procedure)
            db.session.add(procedure)
        # Initialize medication TODO create medication days_after_surgery-times!
        for protocol_anesthesia in PAnesthesia.query.filter(PAnesthesia.protocol == full_protocol):
            for x in range(int(protocol_anesthesia.days_after_surgery)+1):
                anesthetic = Anesthesia(animal_id, protocol_anesthesia, x)
                db.session.add(anesthetic)
        for protocol_analgesia in PAnalgesia.query.filter(PAnalgesia.protocol == full_protocol):
            for x in range(int(protocol_analgesia.days_after_surgery)+1):
                analgesia = Analgesia(animal_id, protocol_analgesia, x)
                db.session.add(analgesia)
        # Initialize viruses
        for protocol_virus in PVirus.query.filter(PVirus.protocol == full_protocol):
            virus = Virus(animal_id, protocol_virus)
            db.session.add(virus)
        db.session.commit()
        return "", 200

    def update_dates(self, animal_id: str, start_date: str) -> Tuple[str, int]:
        """! Updates dates of experiment-data according to protocol-data. 

        @param animal_id  ID of animal 
        @param start_date  Start date based on which dates are filled. 

        @return Tuple of error-message and http-return-code.
        """
        start_date = strtodate(start_date)
        # Update start-date in General
        general = General.query.get(animal_id)
        general.start = datetostr(start_date, SOURCE_DATE_FORMAT)
        surgery_start = get_surgery_start(general.experiment)
        def get_date(inc):
            return datetostr(incdate(start_date, inc), SOURCE_DATE_FORMAT)
        # Update medication:
        def update_medication(table): 
            for x in table.query.filter(table.animal_id == animal_id): 
                x.date = get_date(x.days_after_surgery+surgery_start)
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
        return "", 200

    def update_weights_and_watercontrol(
        self, animal_id: str, weights: str, water_control_mask: str
    ) -> Tuple[str, int]:
        """! Updates a field of in an animal entry. """
        general = self.sql.get("general", animal_id)
        if len(general) == 0:
            return "general data entry (start, end, ...) missing", 401
        general = general[0] 
        general["watercontrol"] = water_control_mask
        general["weights"] = weights
        general["start_weight"] = json.loads(weights)[0]
        self.store_experiment_data(animal_id, {"general": [general]})
        return "success", 200

    def store_experiment_data(
        self, animal_id: str, data: Dict[str, List[Dict[str, any]]]
    ):
        """! Inserts data to sql-database tables. 

        @param animal_id  ID of animal
        @param data  experiment-data.

        @return status code: 200 on success.
        """
        start_date = data["general"][0]["start"] 
        animal_data = self.__get_animal_entry(animal_id)
        sacrifice_date = animal_data["death_date"]
        if start_date > sacrifice_date:
            raise ParserException("start_date must lie before sacrifice_date!", 400)
        for table_name, table_data in data.items():
            # Add animal_id to each entry
            for x in table_data: 
                x["animal_id"] = animal_id
            # Remove old data (TODO check UPSERT option)
            self.sql.delete(animal_id, [table_name])
            # Insert data
            self.sql.insert(table_name, table_data)

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
            data["stored"] = self.__is_stored(data["id"])
        return animal_data

    def generate_weight_list(self, animal_id) -> Tuple[str, int]:
        animal_data = self.__get_animal_entry(animal_id)
        if not date_filled(animal_data["death_date"]): 
            return "Animal is not yet sacrificed", 401
        # Get start-date from general data
        general = self.sql.get("general", animal_id)
        if len(general) == 0:
            return "general data entry (start, end, ...) missing", 401
        general = general[0]  # Only one element. Use this.
        start_date = general["start"]
        if not date_filled(start_date): 
            return "Missing start-date", 401
        # Get protocol-information (watercontrol)
        path = self.__get_protocol_path(animal_id)
        if path is None: 
            return "Protocol or subprotocol not found", 401
        infos = self.__parse_protocal_data(path, "watercontrol")

        # Get some values 
        start_weight = float(general["start_weight"]) if general["start_weight"] != "" else -1
        sacrifice_date = strtodate(animal_data["death_date"])

        # Get start date, date of bearth and calculate age at start
        start_date = strtodate(start_date) 
        dob = strtodate(animal_data["dob"])
        age_at_start = (start_date - dob).days
        duration = len(daterange(start_date, sacrifice_date))

        # Generate water-control-mask
        if len(infos) > 0:
            infos = infos[0] # Only one element. Use this.
            days_after_start = infos["days_after_start"]
            water_restriction_start = incdate(start_date, days_after_start)
            surgery_dates = [incdate(start_date, 2)]  # TODO: find surgery_dates
            duration_water = len(daterange(water_restriction_start, sacrifice_date))
            # Calculate water-control-mask and estimated weights
            water_control_mask = get_water_control_mask(
                water_restriction_start, duration_water, surgery_dates, sacrificed=True
            )
            # Add `False`-values for days_after_start  
            water_control_mask = [False for _ in range(days_after_start)] + water_control_mask
        else:
            water_control_mask = [False for _ in range(duration+1)]
        # Generate estimated weights 
        estimated_weights = get_estimated_weight_list(
            age_at_start, animal_data["sex"], duration, water_control_mask, start_weight
        )
        weights = apply_noise(estimated_weights, 0.070, start_weight==-1);

        # Update general data
        general["watercontrol"] = json.dumps(water_control_mask)
        general["weights"] = json.dumps(weights)
        # Update start-weight as it might have changed
        general["start_weight"] = round(estimated_weights[0], 2)
        self.store_experiment_data(animal_id, {"general": [general]})
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

    def __is_stored(self, animal_id: str) -> bool:
        """! Checks if experiment-data is stored. 

        Checks if animal is dead (`death_date` is filled) and whether
        all experiment-steps are done (assuming that everything is done when
        `start` and `end` or filled)

        @param animal_id  ID of animal.
        @param check_all  If False returns True if ANY data is stored
        @return Boolean indicating whether data is stored or not.
        """
        general = General.query.filter(General.animal_id == animal_id)
        general = general[0] if general.first() else None
        animal_data = self.__get_animal_entry(animal_id)
        return (
            animal_data is not None and general is not None
            and date_filled(animal_data["death_date"])
            and date_filled(general.start)
            and date_filled(general.end)
        )

    def __has_stored_data(self, animal_id: str) -> bool: 
        """! Checks if there is any data stored for a animal sofar.

        @param animal_id  ID of animal 
        @return Boolean indicating whether ANY experiment-data exists for given animal.
        """
        for table_name in self.sql.tables.keys():
            if table_name != T_NOTES and len(self.sql.get(table_name, animal_id, "animal_id")) > 0: 
                return True
        return False

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
