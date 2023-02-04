import json 

path = "backup"

with open(f"{path}.json", "r") as f:
    backup = json.load(f)

for name, data in backup.items(): 
    if name == "analgesia" or name == "anesthesia" or name == "panalgesia" or name == "panesthesia" or name == "amedication": 
        for row in data:
            if row["name"] == "Ketamine / Xylazine":
                row["concentration"] = "12.5 / 1.0"
                row["dosis"] = "125 / 10"
                row["weight_independant"] = False

            elif row["name"] == "Carprofen":
                row["concentration"] = "6"
                row["dosis"] = "5"
                row["weight_independant"] = False

            elif row["name"] == "Buprenorphine":
                row["concentration"] = "0.1"
                row["dosis"] = "0.05"
                row["weight_independant"] = False

            elif row["name"] == "Urethane":
                row["concentration"] = "???"
                row["dosis"] = "???"
                row["weight_independant"] = False

            elif row["name"] == "Lidocaine":
                row["concentration"] = "10-20"
                row["dosis"] = ""
                row["weight_independant"] = True

            elif row["name"] == "Isoflurane":
                row["concentration"] = "1000"
                row["dosis"] = ""

            elif row["name"] == "Isofluran":
                row["concentration"] = "1000"
                row["dosis"] = ""
                row["weight_independant"] = True

with open(f"{path}_2.json", "w") as f:
    json.dump(backup, f)



