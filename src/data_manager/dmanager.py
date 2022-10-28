import clevercsv 
import json
import os
import math
import pandas as pd
from typing import Dict

ANESTHETIC = ["Ketamine / Xylazine", "Isoflurane"]

class DManager:
    def __init__(self, data_path: str):
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

    def get_animal_data(self, filter_tag=None, match=None):
        if filter_tag is None:
            return self.animal_data
        return [entry for entry in self.animal_data if entry[filter_tag] == match]

    def load_protocal_data(self, mouse_id: str): 
        data = self.__get_mouse_entry(mouse_id)
        for filename in os.listdir(self.protocol_path):
            if data["protocol_escaped"] in filename:
                full_path = os.path.join(self.protocol_path, filename)
                medication = self.__parse_protocal_data(full_path, "medication", "Drug name")
                anesthetic, analgesic = self.__medication(medication)
                procedure = self.__parse_protocal_data(full_path, "procedure", "Procedure name")
                procedures, surgery_start = self.__procedure(procedure)
        return anesthetic, analgesic, procedures, surgery_start

    def __medication(self, medication: Dict[str, Dict[str, any]]):
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

    def __procedure(self, procedure: Dict[str, Dict[str, any]]):
        """ 
        Extra parsing for procedure infos. 
        Finds surgery-start (days after begin), sorts by days after surgery
        start and makes sure all values are ints
        """
        # Find surgery_start and do some parsing.
        surgery_start = 0
        for value in procedure: 
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
        sort_obj_list_by(procedure, "days_after_start")
        return procedure, surgery_start

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

