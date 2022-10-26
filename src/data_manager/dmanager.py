import clevercsv 
import json
import os

class DManager:
    def __init__(self, data_path: str):
        with open("resources/mapping.json") as f:
            self.mapping = json.load(f)
        self.data_path = data_path
        self.animal_data = []
        self.users = []

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
        # Rename to mouse-id
        os.rename(tmp_path, os.path.join(self.data_path, data["id"] + ".csv"))

    def __load_csv(self, path: str):
        # Load csv
        df = clevercsv.read_dataframe(path)
        # Iterate over keys and add to data useing mapping.
        data = {}
        for key in df.keys():
            value = df[key].values[0]
            if key in self.mapping:
                data[self.mapping[key]] = value
        # Add to animal data
        self.animal_data.append(data)
        # Check if new user was added.
        if data["user"] not in self.users:
            self.users.append(data["user"])
        # Return data
        return data

