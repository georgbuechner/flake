import sqlite3
from typing import Dict, List

TABLES = {
    "procedures": [
        ["animal_id", "TEXT"], 
        ["name", "TEXT"],
        ["start_date", "TEXT"],
        ["end_date", "TEXT"],
        ["experimenter", "TEXT"]
    ]
}
 
class SqlConnector:
    def __init__(self, path: str):
        try:
            # Connect to DB and create a cursor
            self.cnt = sqlite3.connect(path, check_same_thread=False)
            self.cursor = self.cnt.cursor()
            print("DB Init")
            # Write a query and execute it with cursor
            query = "select sqlite_version();"
            self.cursor.execute(query)
            # Fetch and output result
            result = self.cursor.fetchall()
            print(f"SQLite Version is {result}")
            # Close the cursor
            self.cursor.close()

            # Create tables:
            # Create a exam_hall relation
            self.cnt.execute('''CREATE TABLE IF NOT EXISTS procedures(
                ANIMAL_ID TEXT,
                NAME TEXT,
                START_DATE TEXT,
                END_DATE TEXT,
                EXPERIMENTER TEXT,
                PRIMARY KEY (ANIMAL_ID, NAME)
                );''')

        # Handle errors
        except sqlite3.Error as error:
            print("Error occured - ", error)

    def insert_data_in_table(
        self, table_name: str, animal_id: str, data: List[Dict[str, any]]
    ):
        for entry in data:
            # Delete all current data for this animal
            query = f"DELETE FROM {table_name} WHERE animal_id='{animal_id}'"
            self.cnt.execute(query)
            # Create new data for this animal
            query = f"INSERT INTO {table_name} VALUES('{animal_id}'"
            for value in entry.values():
                query += ", '" + value + "'"
            query += ")"
            self.cnt.execute(query)

    def get_data(self, table_name: str, animal_id: str):
        cursor = self.cnt.execute(f"SELECT * FROM {table_name} WHERE ANIMAL_ID='{animal_id}';")
        data = []
        for i in range(TABLE[table_name]):
        for i in cursor:
            print(str(i[0])+" "+str(i[1])+" "+str(i[2])+" "+str(i[3])+ " "+str(i[4]))



    def __del__(self):
        self.close()

    def close(self):
        # Close DB Connection irrespective of success or failure
        if self.cnt:
            self.cnt.close()
            print("SQLite Connection closed")
