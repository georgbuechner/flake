import json
import math
from flask_sqlalchemy import SQLAlchemy
from typing import Dict, List

db = SQLAlchemy()

class User(db.Model):
    """!An admin user capable of viewing reports.

    @param email  Email address of user
    @param name  Name of user 
    @param password  Hashed password of user 
    @param sal  Salt matching password-hash.
    @param password  Encrypted password for the user

    """
    __tablename__ = 'user'

    email = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, primary_key=False)
    password = db.Column(db.String, primary_key=False)
    salt = db.Column(db.String, primary_key=False)
    authenticated = db.Column(db.Boolean, default=False)

    def is_active(self):
        """! True, as all users are active."""
        return True

    def get_id(self):
        """! Return the email address to satisfy Flask-Login's requirements."""
        return self.email

    def is_authenticated(self):
        """! Return True if the user is authenticated."""
        return self.authenticated

    def is_anonymous(self):
        """! False, as anonymous users aren't supported."""
        return False

class AnimalData(db.Model): 
    __tablename__ = "animal_data" 

    mla_num = db.Column(db.String, primary_key=True)
    sex = db.Column(db.String, primary_key=False)
    line = db.Column(db.String, primary_key=False)
    dob = db.Column(db.String, primary_key=False)
    death_date = db.Column(db.String, primary_key=False)
    user = db.Column(db.String, primary_key=False)
    protocol = db.Column(db.String, primary_key=False)
    protocol_escaped = db.Column(db.String, primary_key=False)
    subprotocol = db.Column(db.String, primary_key=False)
    stored = db.Column(db.Boolean, primary_key=False)

    def __init__(self, data: Dict[str, any]):
        self.mla_num = data["id"]
        self.sex = data["sex"]
        self.line = data["line"]
        self.dob = data["dob"]
        self.death_date = str(data["death_date"])
        self.user = data["user"]
        self.protocol = data["protocol"]
        self.protocol_escaped = data["protocol_escaped"]
        self.subprotocol = "---"
        self.stored = False

    def update(self, data: Dict[str, any]): 
        self.sex = data["sex"]
        self.line = data["sex"]
        self.dob = data["dob"]
        self.death_date = str(data["death_date"])
        self.user = data["user"]
        self.protocol = data["protocol"]
        self.protocol_escaped = data["protocol_escaped"]

class Note(db.Model):
    __tablename__ = "notes" 

    animal_id = db.Column(db.String, primary_key=True)
    category = db.Column(db.String, primary_key=True)
    note = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id: str, category: str, note: str):
        self.animal_id = animal_id
        self.category = category
        self.note = note
    
    def update(self, note: str):
        self.note = note
 
class AMedication(db.Model): 
    __tablename__ = "availible_medication"

    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

    def __init__(
        self, name: str, amount: str, concentration: str, days_after_surgery: str
    ):
        self.name = name 
        self.amount = amount 
        self.concentration = concentration 
        self.days_after_surgery = days_after_surgery

    @classmethod 
    def from_json(cls, m: Dict[str, any]): 
        return cls(m["name"], m["amount"], m["concentration"], m["days_after_surgery"])

    def update(self, medication: Dict[str, any]): 
        self.name = medication["name"] 
        self.amount = medication["amount"]
        self.concentration = medication["concentration"]
        self.days_after_surgery = medication["days_after_surgery"]


class AProcedure(db.Model): 
    __tablename__ = "availible_procedures"

    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)
    surgery = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, name: str, days_after_start: str, duration: str, surgery: bool
    ):
        self.name = name 
        self.days_after_start = days_after_start 
        self.duration = duration 
        self.surgery = surgery

    @classmethod
    def from_json(cls, p: Dict[str, any]): 
        return cls(p["name"], p["days_after_start"], p["duration"], "surgery" in p)

    def update(self, procedure: Dict[str, any]): 
        self.name = procedure["name"] 
        self.days_after_start = procedure["days_after_start"] 
        self.duration = procedure["duration"] 
        self.surgery = "surgery" in procedure

class AVirus(db.Model): 
    __tablename__ = "availible_viruses"

    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

    def __init__(self, name: str, days_after_start: str, amount: str):
        self.name = name 
        self.days_after_start = days_after_start 
        self.amount = amount

    @classmethod 
    def from_json(cls, v: Dict[str, any]): 
        return cls(v["name"], v["days_after_start"], v["amount"])
    
    def update(self, virus: Dict[str, any]): 
        self.name = virus["name"] 
        self.days_after_start = virus["days_after_start"]
        self.amount = virus["amount"]

class PGeneral(db.Model):
    __tablename__ = "protocol_general"

    protocol = db.Column(db.String, primary_key=True) 
    num_availible_animals = db.Column(db.Integer, primary_key=False) 
    death_drug = db.Column(db.String, primary_key=False)
    allowed_users = db.Column(db.String, primary_key=False)

    def __init__(
        self, protocol: str, num_availible_animals: int, death_drug: str, allowed_users: str
    ):
        self.protocol = protocol 
        self.num_availible_animals = num_availible_animals 
        self.death_drug = death_drug 
        self.allowed_users = allowed_users 

    @classmethod 
    def from_json(cls, protocol: str, g: Dict[str, any]): 
        return cls(protocol, g["num_availible_animals"], g["death_drug"], g["allowed_users"])

    def update(self, general: Dict[str, any]): 
        self.num_availible_animals = general["num_availible_animals"]
        self.death_drug = general["death_drug"]
        self.allowed_users = general["allowed_users"]

class PAnesthesia(db.Model): 
    __tablename__ = "protocol_anesthesia"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

    def __init__(
        self, protocol: str, name: str, amount: str, concentration:str, days_after_surgery: str
    ):
        self.protocol = protocol 
        self.name = name 
        self.amount = amount
        self.concentration = concentration
        self.days_after_surgery = days_after_surgery 

    @classmethod
    def from_json(cls, protocol: str, m: Dict[str, any]): 
        return cls(protocol, m["name"], m["amount"], m["concentration"], m["days_after_surgery"])

    def update(self, medication: Dict[str, any]): 
        self.name = medication["name"] 
        self.amount = medication["amount"] 
        self.concentration = medication["concentration"] 
        self.days_after_surgery = medication["days_after_surgery"]
 
class PAnalgesia(db.Model): 
    __tablename__ = "protocol_analgesia"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

    def __init__(
        self, protocol: str, name: str, amount: str, concentration:str, days_after_surgery: str
    ):
        self.protocol = protocol 
        self.name = name 
        self.amount = amount
        self.concentration = concentration
        self.days_after_surgery = days_after_surgery 

    @classmethod
    def from_json(cls, protocol: str, m: Dict[str, any]): 
        return cls(protocol, m["name"], m["amount"], m["concentration"], m["days_after_surgery"])

    def update(self, medication: Dict[str, any]): 
        self.name = medication["name"] 
        self.amount = medication["amount"] 
        self.concentration = medication["concentration"] 
        self.days_after_surgery = medication["days_after_surgery"]
 
class PProcedure(db.Model): 
    __tablename__ = "protocol_procedures"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)
    surgery = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, protocol: str, name: str, days_after_start: str, duration: str, surgery: bool
    ):
        self.protocol = protocol
        self.name = name 
        self.days_after_start = days_after_start 
        self.duration = duration
        self.surgery = surgery

    @classmethod
    def from_json(cls, protocol: str, p: Dict[str, any]): 
        return cls(
            protocol, p["name"], p["days_after_start"], p["duration"], "surgery" in p
        )

    def update(self, procedure: Dict[str, any]): 
        self.name = procedure["name"] 
        self.days_after_start = procedure["days_after_start"] 
        self.duration = procedure["duration"] 
        self.surgery = "surgery" in procedure

class PVirus(db.Model): 
    __tablename__ = "protocol_viruses"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

    def __init__(
        self, protocol: str, name: str, days_after_start: str, amount: str
    ):
        self.protocol = protocol
        self.name = name 
        self.days_after_start = days_after_start 
        self.amount = amount

    @classmethod
    def from_json(cls, protocol: str, v: Dict[str, any]): 
        return cls(protocol, v["name"], v["days_after_start"], v["amount"])

    def update(self, p: Dict[str, any]): 
        self.name = p["name"] 
        self.days_after_start = p["days_after_start"] 
        self.amount = p["amount"] 

class PWatercontrol(db.Model): 
    __tablename__ = "protocol_watercontrol"

    protocol = db.Column(db.String, primary_key=True) 
    allowed = db.Column(db.Boolean, primary_key=False) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)

    def __init__(
        self, protocol: str, allowed: bool, days_after_start: str, duration: str
    ):
        self.protocol = protocol
        self.allowed = allowed
        self.days_after_start = days_after_start 
        self.duration = duration

    @classmethod
    def from_json(cls, protocol: str, w: Dict[str, any]): 
        return cls(protocol, "allowed" in w, w["days_after_start"], w["duration"])

    def update(self, watercontrol: Dict[str, any]): 
        self.allowed = "allowed" in watercontrol
        self.days_after_start = watercontrol["days_after_start"] 
        self.duration = watercontrol["duration"] 

class Protocol(db.Model): 
    __tablename__ = "protocols"

    name = db.Column(db.String, primary_key=False) 
    escaped = db.Column(db.String, primary_key=True)
    subprotocols = db.Column(db.String, primary_key=False)

    def get_subprotocols(self) -> List[str]:
        subprotocols = self.subprotocols.split(";")
        if len(subprotocols) > 0 and subprotocols[0] == "":
            return []
        return subprotocols

    def add_subprotocol(self, subprotocol):
        if len(self.subprotocols) == 0:
            self.subprotocols += subprotocol 
        else:
            self.subprotocols += ";" + subprotocol

    def remove_subprotocol(self, subprotocol):
        subprotocols = self.get_subprotocols() 
        subprotocols.remove(subprotocol)
        self.subprotocols = ";".join(subprotocols)

class General(db.Model):
    __tablename__ = "general"

    animal_id = db.Column(db.String, primary_key=True) 
    start = db.Column(db.String, primary_key=False) 
    end = db.Column(db.String, primary_key=False)
    experiment = db.Column(db.String, primary_key=False)
    start_weight = db.Column(db.Integer, primary_key=False) 
    watercontrol = db.Column(db.Boolean, primary_key=False) 
    weights = db.Column(db.String, primary_key=False)
    watercontrol_mask = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id: str, experiment: str, watercontrol: bool): 
        self.animal_id = animal_id 
        self.start = ""
        self.end = ""
        self.experiment = experiment
        self.start_weight = 0 
        self.watercontrol = watercontrol
        self.weights = json.dumps([])
        self.watercontrol_mask = json.dumps([])

class Anesthesia(db.Model): 
    __tablename__ = "anesthesia"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    toe_pinch = db.Column(db.Boolean, primary_key=False)
    days_after_surgery = db.Column(db.Integer, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        date: str, 
        amount: str, 
        concentration: str, 
        toe_pinch: bool = True,
        days_after_surgery: int = -1
    ):
        """! Initializes Anesthesia. 

        Uses `days_after_surgery` as a placeholder for date, to ensure uniqueness (since
        anesthesia might be added multiple days. Later the dates will be
        succesive dates. 
        """
        self.animal_id = animal_id 
        self.name = name 
        self.date = date
        self.amount = amount 
        self.concentration = concentration 
        self.toe_pinch = toe_pinch
        self.days_after_surgery = days_after_surgery

    @classmethod
    def from_default(cls, animal_id: str, a: PAnesthesia, days_after_surgery: int):
        return cls(
            animal_id, 
            a.name, 
            str(days_after_surgery), 
            a.amount,
            a.concentration, 
            days_after_surgery=days_after_surgery
        )

    @classmethod
    def from_json(cls, animal_id: str, a: Dict[str, any]):
        toe_pinch = "toe_pinch" in a
        return cls(
            animal_id, a["name"], a["date"], a["amount"], a["concentration"], toe_pinch
        )

    def update(self, a: Dict[str, any]):
        self.date = a["date"] 
        self.amount = a["amount"]
        self.concentration = a["concentration"] 
        self.toe_pinch = "toe_pinch" in a 
        print("Changed concentration to: ", self.concentration)

class Analgesia(db.Model): 
    __tablename__ = "analgesia"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.Integer, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        date: str, 
        amount: str, 
        concentration: str, 
        days_after_surgery: int = -1
    ):
        """! Initializes Analgesia. 

        Uses `days_after_surgery` as a placeholder for date, to ensure uniqueness (since
        analgesia might be added multiple days. Later the dates will be
        succesive dates. 
        """
        self.animal_id = animal_id 
        self.name = name 
        self.date = date
        self.amount = amount 
        self.concentration = concentration 
        self.days_after_surgery = days_after_surgery

    @classmethod
    def from_default(cls, animal_id: str, a: PAnalgesia, days_after_surgery: int):
        return cls(
            animal_id, a.name, str(days_after_surgery), a.amount, a.concentration, days_after_surgery
        )

    @classmethod
    def from_json(cls, animal_id: str, a: Dict[str, any]):
        return cls(animal_id, a["name"], a["date"], a["amount"], a["concentration"])

    def update(self, a: Dict[str, any]):
        self.date = a["date"] 
        self.amount = a["amount"]
        self.concentration = a["concentration"] 

class Procedure(db.Model): 
    __tablename__ = "procedures"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    start_date = db.Column(db.String, primary_key=False) 
    end_date = db.Column(db.String, primary_key=False) 
    experimenter = db.Column(db.String, primary_key=False) 

    def __init__(self, animal_id: str, name: str, start: str, end: str, experimenter: str): 
        self.animal_id = animal_id 
        self.name = name 
        self.start_date = start
        self.end_date = end
        self.experimenter = experimenter

    @classmethod 
    def from_default(cls, animal_id: str, experimenter: str, procedure: PProcedure):
        return cls(animal_id, procedure.name, "", "", experimenter)

    @classmethod 
    def from_json(cls, animal_id: str, p: Dict[str, any]): 
        return cls(animal_id, p["name"], p["start_date"], p["end_date"], p["experimenter"])

    def update(self, p: Dict[str, any]):
        self.start_date = p["start_date"]
        self.end_date = p["end_date"]
        self.experimenter = p["experimenter"]

class PostProcedure(db.Model): 
    __tablename__ = "post_procedures"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    start_date = db.Column(db.String, primary_key=False) 
    end_date = db.Column(db.String, primary_key=False) 
    experimenter = db.Column(db.String, primary_key=False) 

    def __init__(self, animal_id: str, name: str, start: str, end: str, experimenter: str): 
        self.animal_id = animal_id 
        self.name = name 
        self.start_date = start
        self.end_date = end
        self.experimenter = experimenter

    @classmethod 
    def from_default(cls, animal_id: str, experimenter: str, procedure: PProcedure):
        return cls(animal_id, procedure.name, "", "", experimenter)

    @classmethod 
    def from_json(cls, animal_id: str, p: Dict[str, any]): 
        return cls(animal_id, p["name"], p["start_date"], p["end_date"], p["experimenter"])

    def update(self, p: Dict[str, any]):
        self.start_date = p["start_date"]
        self.end_date = p["end_date"]
        self.experimenter = p["experimenter"]

    
class Virus(db.Model): 
    __tablename__ = "virus"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id, name: str, date: str, amount: str): 
        self.animal_id = animal_id 
        self.name = name
        self.date = date 
        self.amount = amount

    @classmethod 
    def from_default(cls, animal_id: str, virus: PVirus): 
        return cls(animal_id, virus.name, "", virus.amount)

    @classmethod 
    def from_json(cls, animal_id: str, virus: Dict[str, any]): 
        return cls(animal_id, virus["name"], virus["date"], virus["amount"])

    def update(self, virus: Dict[str, any]):
        self.date = virus["date"]
        self.amount = virus["amount"]

def table_to_json(table): 
    """! Removes fields added by sql-alchamy. """
    return {k:v for (k,v) in table.__dict__.items() if k[0] != "_"}

   

EXPERIMENT_TABLES = {
    "anesthesia": Anesthesia, 
    "analgesia": Analgesia, 
    "procedures": Procedure,
    "post_procedures": PostProcedure,
    "viruses": Virus 
}

PROTOCOL_TABLES = {
    "anesthesia": PAnesthesia, 
    "analgesia": PAnalgesia, 
    "procedures": PProcedure, 
    "viruses": PVirus
}

DEFINITION_TABLES = { 
    "medication": AMedication, 
    "procedures": AProcedure, 
    "viruses": AVirus
}
