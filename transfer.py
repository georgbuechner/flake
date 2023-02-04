import json 

path = "backup"

with open(f"{path}.json", "r") as f:
    backup = json.load(f)

for name, data in backup.items(): 
    if name == "animal_data":
        for row in data:
            row["id"] = row["mla_num"]
    if name == "anesthesia" or name == "analgesia": 
        dates = {}
        for row in data:
            if not row["name"] in dates:
                row["date"] = 0
                dates[row["name"]] = 1
            else: 
                row["date"] = dates[row["name"]]
                dates[row["name"]] += 1



backup.pop("pwatercontrol")

with open(f"{path}_2.json", "w") as f:
    json.dump(backup, f)



