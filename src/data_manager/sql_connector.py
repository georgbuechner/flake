import json
import sqlite3
from collections import OrderedDict
from typing import Dict, List
from utils import sort

class SqlConnector:
    """! The sql-connection class."""

    def __init__(self, db_path: str, tables_path: str):
        """! The SqlConnector initializer. 

        @param db_path  Path to database.
        @param tables_path  Path to json defining tables to create.
        """
        try:
            # Connect to DB and create a cursor
            self.cnt = sqlite3.connect(db_path, check_same_thread=False)
            self.cursor = self.cnt.cursor()
            # Write a query and execute it with cursor
            query = "select sqlite_version();"
            self.cursor.execute(query)
            # Fetch and output result
            result = self.cursor.fetchall()
            print(f"SQLite Version is {result}")
            # Close the cursor
            self.cursor.close()

            # Create tables from tables-json:
            with open(tables_path) as f:
                self.tables = json.load(f)
            # Make sure table names are sorted alphabetically.
            for table_name, table_data in self.tables.items():
                # Create query:
                query = f"CREATE TABLE IF NOT EXISTS {table_name}("
                for row in sort(table_data["rows"], "name"):
                    query += row["name"] + " " + row["type"] + ", "
                query += f"PRIMARY KEY ({table_data['primary_keys']}));"
                # execute query:
                self.cnt.execute(query)
                print(f"SqlConnector: created table {table_name}")
        # Handle errors
        except sqlite3.Error as error:
            print("Error occured - ", error)

    def insert_plus_animal_id(
        self, table_name: str, animal_id: str, data: List[Dict[str, any]]
    ):
        """! Inserts new experiment-data into database.

        Deletes all existing experiment-data for this animal, then adds
        animal-id to each entry in data and calls regular insert-method.

        @param table_name  Name of table into which to insert data.
        @param animal_id  ID of animal.
        @param data  Data to store.
        """
        # Delete all current data for this animal (TODO: check UPSERT option)
        self.cnt.execute(f"DELETE FROM {table_name} WHERE animal_id='{animal_id}'")
        # Add animal_id to each entry
        for x in data: 
            x["animal_id"] = animal_id
        self.insert(table_name, data)

    def insert(self, table_name: str, data: List[Dict[str, any]]):
        """! Inserts new experiment-data into database.

        @param table_name  Name of table into which to insert data.
        @param animal_id  ID of animal.
        @param data  Data to store.
        """
        for entry in data:
            # Create new data for this animal
            query = f"INSERT INTO {table_name} VALUES("
            # Make sure data is inserted alphabetically.
            sorted_entry = OrderedDict(sorted(entry.items()))
            for value in sorted_entry.values():
                query += f"'{value}', "
            query = query[:-2] + ")"  # Remove trailing ', ' and add closing bracket.
            self.cnt.execute(query)
        self.cnt.commit()

    def get(
        self, table_name: str, key: str, filter_tag: str="animal_id"
    ) -> List[Dict[str, any]]:
        """! Gets data from database.

        @param table_name  Name of table from which to get data.
        @param filter_tag  Table key by which to check 
        @param key  ID of animal.

        @return Data extracted from database as list of dictionaries.
        """
        try:
            query = f"SELECT * FROM {table_name}"
            if key is not None and filter_tag is not None: 
                query += f" WHERE {filter_tag}='{key}'"
            query + ";"
            cursor = self.cnt.execute(query)
        except sqlite3.Error as error:
            print(f"No data found in table {table_name} for {key}")
            return []
        data = []
        for col in cursor:
            entry = {}
            for index, row in enumerate(self.tables[table_name]["rows"]):
                entry[row["name"]] = col[index]
            data.append(entry)
        return data

    def get_all(self, table_name: str, key: str) -> List[str]: 
        try:
            query = f"SELECT {key} FROM {table_name};"
            cursor = self.cnt.execute(query)
        except sqlite3.Error as error:
            print(f"No data found in table {table_name} for {key}")
            return []
        all_xs = set()
        for col in cursor:
            all_xs.add(col[0])
        return list(all_xs)


    def __del__(self):
        """! Destructor closing database connection."""
        # Close DB Connection irrespective of success or failure
        if self.cnt:
            self.cnt.close()
