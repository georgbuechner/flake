import json
import sqlite3
from typing import Dict, List

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
            for table_name, table_data in self.tables.items():
                # Create query:
                query = f"CREATE TABLE IF NOT EXISTS {table_name}("
                for row in table_data["rows"]:
                    query += row["name"] + " " + row["type"] + ", "
                query += f"PRIMARY KEY ({table_data['primary_keys']}));"
                # execute query:
                self.cnt.execute(query)
        # Handle errors
        except sqlite3.Error as error:
            print("Error occured - ", error)

    def insert(
        self, table_name: str, animal_id: str, data: List[Dict[str, any]]
    ):
        """! Inserts new data into database.

        @param table_name  Name of table into which to insert data.
        @param animal_id  ID of animal.
        @param data  Data to store.
        """
        # Delete all current data for this animal (TODO: check UPSERT option)
        query = f"DELETE FROM {table_name} WHERE animal_id='{animal_id}'"
        self.cnt.execute(query)
        for entry in data:
            # Create new data for this animal
            query = f"INSERT INTO {table_name} VALUES('{animal_id}'"
            for value in entry.values():
                query += f", '{value}'"
            query += ")"
            self.cnt.execute(query)
        self.cnt.commit()

    def get(self, table_name: str, animal_id: str) -> List[Dict[str, any]]:
        """! Gets data from database.

        @param table_name  Name of table from which to get data.
        @param animal_id  ID of animal.

        @return Data extracted from database as list of dictionaries.
        """

        try:
            cursor = self.cnt.execute(f"SELECT * FROM {table_name} WHERE ANIMAL_ID='{animal_id}';")
        except sqlite3.Error as error:
            print(f"No data found in table {table_name} for {animal_id}")
            return []
        # print(f"Found {len([x for x in cursor])} entries in table {table_name} for {animal_id}")
        data = []
        for col in cursor:
            entry = {}
            for index, row in enumerate(self.tables[table_name]["rows"]):
                entry[row["name"]] = col[index]
            data.append(entry)
        return data

    def __del__(self):
        """! Destructor closing database connection."""
        # Close DB Connection irrespective of success or failure
        if self.cnt:
            self.cnt.close()
