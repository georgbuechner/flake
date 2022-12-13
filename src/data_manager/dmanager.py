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
from utils.utils import sort
from utils.dt_utils import strtodate, datetostr, incdate, daterange

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
        self.protocols = {}
        self.mapping = {}
        self.keys_per_language = {}
        with open("resources/mapping.json") as f:
            mapping = json.load(f)
            for language, fields in mapping.items():
                self.mapping.update(fields)
                self.keys_per_language[language] = fields.keys()
        # Update protocol information:
        self.__update_availible_protocols()

    def users(self) -> List[str]: 
        """! Gets list of all users (pyrat: 'Responsible') which are currently
        responsible for an animal.

        @return List of users.
        """
        return self.sql.get_all(T_ANIMAL_DATA, "user")

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
        self.__update_availible_protocols()
        inserted_msg =f"{total-len(updated)} inserted."
        if len(updated) == 0:
            return inserted_msg, 200
        updated_msg = f"{len(updated)} updated ({' '.join(x for x in updated)})"
        return inserted_msg + " " + updated_msg, 206 

    def update_animal_field(
        self, animal_id: str, field: str, subprotocol: str
    ) -> Tuple[str, int]:
        """! Updates a field of in an animal entry. """
        res = self.sql.update(T_ANIMAL_DATA, {"id":animal_id}, {field:subprotocol})
        if res:
            return "", 200
        return "An error occured, we're sorry", 500

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

    def clear_experiment_data( self, animal_id: str) -> int:
        """! Clears experiment-data for animal

        @param animal_id  ID of animal

        @return status code: 200 on success.
        """
        self.sql.delete(animal_id, self.sql.experiment_data_tables)
        return 200

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

    def load_protocal_data(self, animal_id: str) -> ExperimentData: 
        """! Loads protocol-data for given animal-id.

        Either sends default-data matching protocol for given animal, or loads
        data already stored for this animal.

        @param animal_id  ID of animal to store experiment-data for.

        @return experiment-data (default or stored).
        """
        # Load animal-data and default-data for given animal-id:
        animal_data = self.__get_animal_entry(animal_id)
        experiment_data = self.__load_default_values(animal_id)
        # If data exists in database, overwrite default values.
        if self.__has_stored_data(animal_id):
            experiment_data.stored = True
            experiment_data.set_general(self.sql.get("general", animal_id)[0])
            experiment_data.procedures = sort(self.sql.get("procedures", animal_id), "start_date")
            experiment_data.post_procedures = sort(
                self.sql.get("post_procedures", animal_id), "start_date"
            )
            experiment_data.anesthetic = self.sql.get("anesthetic", animal_id)
            experiment_data.analgesic = sort(self.sql.get("analgesic", animal_id), "date")
            experiment_data.viruses = sort(self.sql.get("viruses", animal_id), "date")
        return experiment_data

    def generate_weight_list(self, animal_id) -> Tuple[str, int]:
        animal_data = self.__get_animal_entry(animal_id)
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
        is_sacrificed = date_filled(animal_data["death_date"])
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
                water_restriction_start, duration_water, surgery_dates, sacrificed=is_sacrificed
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

    def get_protocol(self, animal_id: str) -> str: 
        animal_data = self.__get_animal_entry(animal_id)
        protocol = animal_data["protocol"]
        subprotocol = animal_data["subprotocol"]
        if protocol in self.protocols and subprotocol in self.protocols[protocol]["subs"]:
            return self.protocols[protocol]["escaped"] + "_" + subprotocol
        return "";

    def __load_default_values(self, animal_id: str) -> ExperimentData:
        """! Loads default experiment-data for given protocol.

        @param protocol  Protocol for which to load data.
        
        @return Experiment-data
        """
        # Check if protocol-data exists and get path to protocol-data: 
        path = self.__get_protocol_path(animal_id)
        if path is None: 
            return None
        # medication
        medication = self.__parse_protocal_data(path, "medication")
        anesthetic, analgesic = self.__medication(medication)
        # procedures
        procedures = self.__parse_protocal_data(path, "procedure")
        procedures, post_procedures, surgery_start = self.__procedure(procedures)
        # viruses 
        viruses = self.__parse_protocal_data(path, "Virus")
        # General 
        general = {} 
        animal_data = self.__get_animal_entry(animal_id)
        general["experiment"] = animal_data["protocol"] + " " + animal_data["subprotocol"]
        # Create experiment-data from parsed values
        return ExperimentData(
            stored=False, 
            general=general, 
            viruses=viruses, 
            anesthetic=anesthetic, 
            analgesic=analgesic, 
            procedures=procedures, 
            post_procedures=post_procedures, 
            surgery_start=surgery_start
        )

    def __medication(
        self, medication: List[Dict[str, any]]
    ) -> Tuple[List[Dict[str, any]], List[Dict[str, any]]]:
        """! Handles extra parsing for medication infos. 

        Anesthetic and analgesic drugs are seperated according to pre-defined
        durgs in ANESTHETIC field.

        @param medication Unprocessed default-medication-data.

        @return Seperated anesthetic and analgesic data
        """
        # Seperate anesthetic and analgesic
        anesthetic = [entry for entry in medication if entry["name"] in ANESTHETIC]
        analgesic = [entry for entry in medication if entry["name"] not in ANESTHETIC]
        sort(analgesic, DAYS_AFTER_SURGERY)
        return anesthetic, analgesic

    def __procedure(
        self, procedures: List[Dict[str, any]]
    ) -> Tuple[List[Dict[str, any]], List[Dict[str, any]], int]:
        """! Handles extra parsing for procedure infos. 

        Finds surgery-start (days after begin), sorts by days-after-start
        and makes sure all values are intergers.
        Splits procedures into procedures and post-procedures.

        @param procedures  Unprocessed default-procedure-data.

        @return Procedures, post-procedures and surgery-start (as days after start).
        """
        # Find surgery_start and do some parsing.
        surgery_start = 0
        for value in procedures: 
            # Find surgery-start (days_after_start from any element with surgery?=yes):
            if value["surgery?"] == "yes":
                surgery_start = value[DAYS_AFTER_START]
            # Make sure days_after_start is interger:
            value[DAYS_AFTER_START] = int(value[DAYS_AFTER_START])
            # Make sure duration_in_days is interger:
            if isinstance(value[DURATION_IN_DAYS], str) and "-" in value[DURATION_IN_DAYS]:
                value[DURATION_IN_DAYS] = random.randint(
                    int(value[DURATION_IN_DAYS].split("-")[0]), 
                    int(value[DURATION_IN_DAYS].split("-")[1])
                )
            else:
                value[DURATION_IN_DAYS] = int(value[DURATION_IN_DAYS])
        # Sort:
        sort(procedures, DAYS_AFTER_START)
        # Split in pre_procedures and post_procedures
        post_procedures = [p for p in procedures if p[DAYS_AFTER_START] > surgery_start]
        procedures = [p for p in procedures if p[DAYS_AFTER_START] <= surgery_start]
        return procedures, post_procedures, surgery_start

    def __parse_protocal_data(self, path: str, sheet_name: str) -> List[Dict[str, any]]:
        """! Parses default-protocol data.

        @param path  Path to protocol-data.
        @param sheet_name  Sheet which to get data from.
        @return All default-data with attribute where `allowed` is `yes`.
        """
        df = pd.read_excel(path, sheet_name=sheet_name) 
        data = df.to_dict("records")
        # Remove all not allowed
        return [entry for entry in data if "allowed" not in entry or entry["allowed"] == "yes"]

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
                self.sql.update_animal_data(T_ANIMAL_DATA, {"id":data["id"]}, data)
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

    def __update_availible_protocols(self):
        protocol_path = os.path.join("resources", "protocols")
        protocols = self.sql.get_all(T_ANIMAL_DATA, "protocol")
        protocols_data = {}
        for protocol in protocols:
            espaped = escape_protocol(protocol)  # generate escaped name for url-display
            data = {"escaped": espaped, "subs": {}}
            for filename in os.listdir(protocol_path):
                if espaped in filename and "~lock" not in filename:
                    # Get path and subprotocol-letter
                    path = os.path.join(protocol_path, filename)
                    subprotocol_letter = filename[-6]
                    # Get allowed users
                    users = self.__parse_protocal_data(path, "users")
                    # Generate subprotocol-data with path and empty users-list
                    sub_data = {"path": path, "users": [x["name"] for x in users]}
                    data["subs"][subprotocol_letter] = sub_data
            self.protocols[protocol] = data

    def __is_stored(self, animal_id: str) -> bool:
        """! Checks if experiment-data is stored. 

        Checks if animal is dead (`death_date` is filled) and whether
        all experiment-steps are done (assuming that everything is done when
        `start` and `end` or filled)

        @param animal_id  ID of animal.
        @param check_all  If False returns True if ANY data is stored
        @return Boolean indicating whether data is stored or not.
        """
        experiment_data = self.sql.get("general", animal_id, "animal_id")
        # Take first element, since 'general' has only one entry for each animal
        experiment_data = experiment_data[0] if len(experiment_data) > 0 else None
        animal_data = self.__get_animal_entry(animal_id)
        return (
            animal_data is not None and experiment_data is not None
            and date_filled(animal_data["death_date"])
            and date_filled(experiment_data["start"])
            and date_filled(experiment_data["end"])
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

    def __get_protocol_path(self, animal_id: str) -> str: 
        """! Gets path to protocol-infos from animal id. 

        @param animal_id  ID of animal
        @return Path to protocol-spreadsheet if exists, None otherwise.
        """
        animal_data = self.__get_animal_entry(animal_id)
        protocol = animal_data["protocol"]
        subprotocol = animal_data["subprotocol"]
        if protocol in self.protocols and subprotocol in self.protocols[protocol]["subs"]:
            return self.protocols[protocol]["subs"][subprotocol]["path"]
        else:
            print(f"{protocol} or {subprotocol} not in {self.protocols}")
            return None 

def date_filled(date_str: str) -> bool: 
    return len(date_str) == 10


def escape_protocol(protocol: str) -> str: 
    """! Escape protocol-string to be url compatible. 

    Removes whitespaces (" ") and replaces slashs ("/") underscore ("_").
    
    @param protocol  Protocol-name.
    @return Escaped protocol-name.
    """
    return protocol.replace(" ", "").replace("/", "_")
