import json 

path = "backup"

with open(f"{path}.json", "r") as f:
    backup = json.load(f)

def get_key(name, row): 
    if name[0] == "a":
        return row["name"]
    elif name[0] == "p":
        return row["name"] + row["protocol"]
    else:
        return row["name"] + row["animal_id"] + row["procedure"]

amedication = []
pmedication = []
medication = []
for name, data in backup.items(): 
    if name == "analgesia" or name == "anesthesia" or name == "panalgesia" or name == "panesthesia" or name == "amedication": 

        # Remove dublicates (only keep entry with largest `days_after_surgery`
        rows = []
        names = {}
        for row in data:
            key = get_key(name, row)
            if key not in names:
                names[key] = int(row["days_after_surgery"])
            elif names[key] < int(row["days_after_surgery"]): 
                names[key] = int(row["days_after_surgery"])
        for row in data: 
            key = get_key(name, row)
            if int(row["days_after_surgery"]) == names[key]: 
                rows.append(row)

        # Convert to new:
        for row in rows:
            if "dosis" not in row:
                if row["name"] == "Ketamin":
                    row["dosis"] = "125"
                elif row["name"] == "Xylazin":
                    row["dosis"] = "10"
                elif row["name"] == "Ketamin/ Xylazin":
                    row["dosis"] = "125 / 10"
                elif row["name"] == "Carprofen":
                    row["dosis"] = "5"
                elif row["name"] == "Buprenofen":
                    row["dosis"] = "0.1"
                else:
                    row["dosis"] = ""

            med_entry = {
                "name": row["name"], 
                "days_after_surgery": row["days_after_surgery"], 
                "amount": row["amount"], 
                "concentration": row["concentration"], 
                "dosis": row["dosis"], 
                "days_after_surgery": row["days_after_surgery"],
                "toe_pinch": "yes",
            }
            if row["days_after_surgery"] == -1: 
                med_entry["procedure"] = "Sacrifice: Decapitation" 
            elif row["days_after_surgery"] == 3: 
                med_entry["procedure"] = "post-operative analgesic" 
            elif row["days_after_surgery"] == 2: 
                med_entry["procedure"] = "post-operative analgesic" 
            else:
                med_entry["procedure"] = "Viral injection" 

            med_entry["kind"] = "analgesia" if "analgesia" in name else "anesthesia"
            if name == "analgesia" or name == "anesthesia":
                med_entry["animal_id"] = row["animal_id"]
                med_entry["protocol_entry_uuid"] = row["protocol_entry_uuid"]
                medication.append(med_entry)
            elif name == "panalgesia" or name == "panesthesia": 
                med_entry["uuid"] = row["uuid"]
                med_entry["protocol"] = row["protocol"]
                pmedication.append(med_entry)
            else: 
                amedication.append(med_entry)

backup["amedication"] = amedication
backup["pmedication"] = pmedication
backup["medication"] = medication
backup.pop("panesthesia")
backup.pop("panalgesia")
backup.pop("analgesia")
backup.pop("anesthesia")

with open(f"{path}_2.json", "w") as f:
    json.dump(backup, f)



