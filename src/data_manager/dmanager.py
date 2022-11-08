import clevercsv 
import json
import os
import math
import random
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from data_manager.sql_connector import SqlConnector
from utils import sort

ANESTHETIC = ["Ketamine / Xylazine", "Isoflurane"]
# Some important keys
DAYS_AFTER_START = "days_after_start"
DAYS_AFTER_SURGERY = "days_after_surgery"
DURATION_IN_DAYS = "duration_in_days"
# Main tables
T_ANIMAL_DATA = "animal_data"

@dataclass
class ExperimentData: 
    """! The experiment-data DTO class."""
    stored: bool
    general: Dict[str, any]
    anesthetic: List[Dict[str, any]]
    analgesic: List[Dict[str, any]]
    procedures: List[Dict[str, any]]
    post_procedures: List[Dict[str, any]]
    surgery_start: int 
    availible_anesthetic: List[str] = field(default_factory=list)
    availible_analgesic: List[str] = field(default_factory=list)

    def __post_init__(self):
        """! Generates availible anesthetic/ anesthetic from given data. """
        self.availible_anesthetic = [x["name"] for x in self.anesthetic]
        self.availible_analgesic = [x["name"] for x in self.analgesic]

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
    """

    def __init__(self, data_path: str, sql_connector: SqlConnector):
        """! The DManager class initializer. 

        @param data_path  path to pyrat-data.
        @param sql_connector  sql-connector-class.
        """
        print(f"Initializing DManager from {data_path}")
        self.sql = sql_connector
        self.mapping = {}
        self.keys_per_language = {}
        with open("resources/mapping.json") as f:
            mapping = json.load(f)
            for language, fields in mapping.items():
                self.mapping.update(fields)
                self.keys_per_language[language] = fields.keys()
        self.data_path = data_path
        self.protocol_path = os.path.join("resources", "protocols")

    def extract_animal_data(self, tmp_path: str, file) -> int:
        """! Extracts and stores animal-data from csv file.

        @param tmp_path  Path for temporarily storing csv-file.

        @return status code: 409 if data for animal_id already exists 200 otherwise.
        """
        # temporarily store file
        file.save(tmp_path)
        # Load file
        existed, total = self.__load_animal_data_from_csv(tmp_path)
        if existed is None: 
            return (f"CSV has missing keys, required: "
                + f"{' '.join(x for x in self.keys['en'])}"
                + f"or {' '.join(x for x in self.keys['en'])}")
        # If none (animal_id already exists)
        os.remove(tmp_path)
        if len(existed) == 0:
            return "", 200
        return f"{len(existed)}/{total} already existed: {' '.join(x for x in existed)}", 206 

    def store_experiment_data(
        self, animal_id: str, data: Dict[str, List[Dict[str, any]]]
    ) -> int:
        """! Inserts data to sql-database tables. 

        @param animal_id  ID of animal
        @param data  experiment-data.

        @return status code: 200 on success.
        """
        for table_name, table_data in data.items():
            print(f"store {table_data} to {table_name}")
            self.sql.insert_plus_animal_id(table_name, animal_id, table_data)
        return 200

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
            data["stored"] = self.is_stored(data["id"])
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
        experiment_data = self.__load_default_values(animal_data["protocol_escaped"])
        # If data exists in database, overwrite default values.
        if self.is_stored(animal_id):
            experiment_data.stored = True
            experiment_data.general = self.sql.get("general", animal_id)[0]
            experiment_data.procedures = sort(
                self.sql.get("procedures", animal_id), DAYS_AFTER_START
            )
            experiment_data.post_procedures = sort(
                self.sql.get("post_procedures", animal_id), DAYS_AFTER_START
            )
            experiment_data.anesthetic= self.sql.get("anesthetic", animal_id)
            experiment_data.analgesic = sort(
                self.sql.get("analgesic", animal_id), DAYS_AFTER_SURGERY
            )
        return experiment_data

    def __load_default_values(self, protocol:str) -> ExperimentData:
        """! Loads default experiment-data for given protocol.

        @param protocol  Protocol for which to load data.
        
        @return Experiment-data
        """
        for filename in os.listdir(self.protocol_path):
            if protocol in filename:
                full_path = os.path.join(self.protocol_path, filename)
                # medication
                medication = self.__parse_protocal_data(full_path, "medication")
                anesthetic, analgesic = self.__medication(medication)
                # procedures
                procedures = self.__parse_protocal_data(full_path, "procedure")
                procedures, post_procedures, surgery_start = self.__procedure(procedures)
        # Create experiment-data from parsed values
        return ExperimentData(
            False, {}, anesthetic, analgesic, procedures, post_procedures, surgery_start
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
        return [entry for entry in data if entry["allowed"] == "yes"]

    def __load_animal_data_from_csv(self, path: str):
        """! Loads animal-data from CSV file.

        @param path  Path to CSV. 
        @return Newly created animal-data, None if data already existed.
        """
        # Load csv
        df = clevercsv.read_dataframe(path)
        if self.__check_all_keys == False: 
            return None, None
        # Iterate over keys and add to data useing mapping.
        existed = []
        for _, row in df.iterrows():
            data = {}
            for key in df.keys():
                value = row[key]
                if key in self.mapping:
                    data[self.mapping[key]] = value
                    if self.mapping[key] == "protocol":
                        data["protocol_escaped"] = value.replace(" ", "").replace("/", "_")
            # If no already exists:
            if len(self.sql.get(T_ANIMAL_DATA, data["id"], "id")) == 0:
                self.sql.insert(T_ANIMAL_DATA, [data])
            else: 
                existed.append(data["id"])
        return existed, len(df)

    def __check_all_keys(self, df): 
        for language_keys in self.keys_per_language.values():
            if all(key in df.keys() for key in language_keys):
                return True
        return False

    def __get_animal_entry(self, animal_id: str):
        """! Gets single entry from animal-data matching given ID.

        @param animal_id  ID of animal to search for.

        @return Entry for given ID or `None` if ID was not found.
        """
        animal_data = self.sql.get(T_ANIMAL_DATA, animal_id, "id")
        if len(animal_data) > 0:
            return animal_data[0]
        return None

    def is_stored(self, animal_id: str) -> bool:
        """! Checks if experiment-data is stored. 

        Only table "general" is check to reduced database access.

        @param animal_id  ID of animal.
        
        @return Boolean indicating whether data is stored or not.
        """
        return len(self.sql.get("general", animal_id, "animal_id")) > 0

    def users(self) -> List[str]: 
        return self.sql.get_all(T_ANIMAL_DATA, "user")

    def protocols(self) -> List[str]: 
        return self.sql.get_all(T_ANIMAL_DATA, "protocol_escaped")
