import clevercsv 
import json
import os
import math
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Tuple
from data_manager.sql_connector import SqlConnector

ANESTHETIC = ["Ketamine / Xylazine", "Isoflurane"]

@dataclass
class ExperimentData: 
    stored: bool
    anesthetic: List[Dict[str, any]]
    analgesic: List[Dict[str, any]]
    procedures: List[Dict[str, any]]
    post_procedures: List[Dict[str, any]]
    surgery_start: int 


class DManager:
    def __init__(self, data_path: str, sql_connector: SqlConnector):
        print(f"Initializing DManager from {data_path}")
        self.sql = sql_connector
        with open("resources/mapping.json") as f:
            self.mapping = json.load(f)
        self.data_path = data_path
        self.protocol_path = os.path.join("resources", "protocols")
        self.animal_data = []
        self.users = []
        self.protocols = []

    def load_data(self):
        # Iterate over all files in data-folder
        for filename in os.listdir(self.data_path):
            full_path = os.path.join(self.data_path, filename)
            if os.path.isfile(full_path):
                self.__load_csv(full_path)
    
    def upload_csv(self, tmp_path: str, file):
        # temporarily store file
        file.save(tmp_path)
        # Load file
        data = self.__load_csv(tmp_path)
        # If None (mouse_id already exists)
        if data is None:
            os.remove(tmp_path)
            return 409
        # Otherwise, rename file to mouse-id and move to data folder
        else:
            os.rename(tmp_path, os.path.join(self.data_path, data["id"] + ".csv"))
            return 200

    def store(
        self, animal_id: str, data: Dict[str, List[Dict[str, any]]]
    ) -> int:
        """ Inserts data to sql-database tables. Returns status code"""
        for table_name, table_data in data.items():
            self.sql.insert_data_in_table(table_name, animal_id, table_data)
            # Test:
            self.sql.get_data(table_name, animal_id)
        return 200


    def get_animal_data(self, filter_tag=None, key=None):
        if filter_tag is None:
            return self.animal_data
        return [entry for entry in self.animal_data if entry[filter_tag] == key]

    def load_protocal_data(self, mouse_id: str) -> ExperimentData: 
        # Check if data exists in database:


        # Otherwise load default data
        data = self.__get_mouse_entry(mouse_id)
        for filename in os.listdir(self.protocol_path):
            if data["protocol_escaped"] in filename:
                full_path = os.path.join(self.protocol_path, filename)
                medication = self.__parse_protocal_data(full_path, "medication", "Drug name")
                anesthetic, analgesic = self.__medication(medication)
                procedures = self.__parse_protocal_data(full_path, "procedure", "Procedure name")
                procedures, post_procedures, surgery_start = self.__procedure(procedures)
        # Create experiment-data from parsed values
        experiment_data = ExperimentData(
            anesthetic, analgesic, procedures, post_procedures, surgery_start
        )
        return experiment_data

    def __medication(
        self, medication: List[Dict[str, any]]
    ) -> Tuple[List[Dict[str, any]], List[Dict[str, any]]]:
        """ 
        Extra parsing for medication infos. 
        anesthetic and analgesic drugs are seperated according to pre-defined
        durgs in ANESTHETIC field.
        """
        # Seperate anesthetic and analgesic
        anesthetic = [entry for entry in medication if entry["Drug name"] in ANESTHETIC]
        analgesic = [entry for entry in medication if entry["Drug name"] not in ANESTHETIC]
        sort_obj_list_by(analgesic, "days_after_surgery")
        return anesthetic, analgesic

    def __procedure(
        self, procedures: List[Dict[str, any]]
    ) -> Tuple[List[Dict[str, any]], List[Dict[str, any]], int]:
        """ 
        Extra parsing for procedure infos. 
        Finds surgery-start (days after begin), sorts by days after surgery
        start and makes sure all values are ints
        """
        # Find surgery_start and do some parsing.
        surgery_start = 0
        for value in procedures: 
            # Find surgery-start (days_after_start from any element with surgery?=yes)
            if value["surgery?"] == "yes":
                surgery_start = value["days_after_start"]
            # And make sure days_after_start is interger
            value["days_after_start"] = int(value["days_after_start"])
            # And make sure duration_in_days is interger (user first element if range
            if isinstance(value["duration_in_days"], str) and "-" in value["duration_in_days"]:
                value["duration_in_days"] = int(value["duration_in_days"].split("-")[0])
            else:
                value["duration_in_days"] = int(value["duration_in_days"])
        # Sort:
        sort_obj_list_by(procedures, "days_after_start")
        # Split in pre_procedures and post_procedures
        post_procedures = [
            entry for entry in procedures if entry["days_after_start"] > surgery_start
        ]
        procedures = [
            entry for entry in procedures if entry["days_after_start"] <= surgery_start
        ]
        return procedures, post_procedures, surgery_start

    def __parse_protocal_data(self, path: str, sheet_name: str, index_name: str):
        df = pd.read_excel(path, sheet_name=sheet_name) 
        data = df.to_dict("records")
        # Remove all not allowed
        return [entry for entry in data if entry["allowed"] == "yes"]

    def __load_csv(self, path: str):
        # Load csv
        df = clevercsv.read_dataframe(path)
        # Iterate over keys and add to data useing mapping.
        data = {}
        for key in df.keys():
            value = df[key].values[0]
            if key in self.mapping:
                data[self.mapping[key]] = value
                if self.mapping[key] == "protocol":
                    data["protocol_escaped"] = value.replace(" ", "").replace("/", "_")
        # If already exists, return None.
        if self.__get_mouse_entry(data["id"]) is not None:
            return None
        # Add to animal data
        self.animal_data.append(data)
        # Check if new user was added.
        if data["user"] not in self.users:
            self.users.append(data["user"])
        if data["protocol_escaped"] not in self.protocols:
            self.protocols.append(data["protocol_escaped"])
        # Return data
        return data

    def __get_mouse_entry(self, mouse_id: str):
        for entry in self.animal_data:
            if entry["id"] == mouse_id:
                return entry
        return None


def sort_obj_list_by(obj_list, key):
    def sort_by_key(e):
        return e[key]
    obj_list.sort(key=sort_by_key)
    return obj_list

