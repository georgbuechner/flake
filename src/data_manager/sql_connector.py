import json
import sqlite3
from collections import OrderedDict
from typing import Dict, List
from utils.utils import sort

class SqlConnector:
    """! The sql-connection class."""

    def __init__(self, db_path: str, tables_path: str):
        """! The SqlConnector initializer. 

        @param db_path  Path to database.
        @param tables_path  Path to json defining tables to create.
        """
        # Create tables from tables-json:
        with open(tables_path) as f:
            self.tables = json.load(f)
        self.experiment_data_tables = [x for x in self.tables.keys() if x != "animal_data"]

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

    def insert(self, table_name: str, data: List[Dict[str, any]]):
        """! Inserts new data into database.

        @param table_name  Name of table into which to insert data.
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
            print(query)
        self.cnt.commit()

    def delete(self, animal_id: str, tables: List[str]):
        for table_name in tables:
            self.cnt.execute(f"DELETE FROM {table_name} WHERE animal_id='{animal_id}'")
        self.cnt.commit()

    def update_animal_data(
        self, table_name: str, entry_id: str, fields: Dict[str, any]
    ) -> bool:
        """! Updates entry in animal-data table. 

        If fields are not specified updates all fields in table, except primary keys.
        
        @param table_name  Name of the table for which entries shall be updated.
        @param entry_id  ID of entry which shall be updated.
        @param values  List of values which to update. 
        @param fields  List of fields which to update.
        @return Boolean indicating success/ failure.
        """
        # Avoid updating primary fields
        primary_keys = self.tables[table_name]["primary_keys"].split(", ")
        print(primary_keys)
        fields = {k:v for (k,v) in fields.items() if k.upper() not in primary_keys}
        print(fields)
        # Generate query to update only given fields and only of given entry_id:
        query = f"UPDATE {table_name} SET"
        for field, value in fields.items(): 
            query += f" {field}='{value}',"
        query = query[:-1] + f" WHERE id='{entry_id}';"  # Remove trailing ',' and WHERE part.
        print(query)
        # Execute:
        try: 
            self.cnt.execute(query)
            self.cnt.commit()
            return True
        except sqlite3.Error as error:
            print("Error occured - ", error)
        return False

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

    def __get_table_fields(
        self, table_name: str, no_primary_keys: bool=False
    ) -> List[str]:
        """! Gets all fields of given table. 

        If `no_primary_keys` is True, excludes primary-keys from result list.
        @param table_name  Name of table to get fields from. 
        @param no_primary_keys  Whether or not to include primary_keys (default: False)
        @return List of all fields of given table.
        """
        table_fields = [row["name"] for row in self.tables[table_name]["rows"]]
        if no_primary_keys:
            primary_keys = self.tables[table_name]["primary_keys"].split(", ")
            table_fields = [field for field in table_fields if field not in primary_keys]
        return table_fields

    def __del__(self):
        """! Destructor closing database connection."""
        # Close DB Connection irrespective of success or failure
        if self.cnt:
            self.cnt.close()
