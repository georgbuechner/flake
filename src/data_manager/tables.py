import json
import math
import uuid
from flask_sqlalchemy import SQLAlchemy
from typing import Dict, List
from utils.dt_utils import date_filled

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

    def __init__(email: str, name: str, password: str, salt: str):
        self.email = email 
        self.name = name 
        self.password = password 
        self.salt = salt

    @classmethod 
    def from_json(cls, user: Dict[str, any]): 
        return cls(
            user["email"], user["name"], user["password"], user["salt"]
        )

    def to_json(self):
        return {
            "email": self.email, "name":self.name, "password": self.password, "salt": self.salt,
        }

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
    protocol_pyrat = db.Column(db.String, primary_key=False)
    protocol = db.Column(db.String, primary_key=False)
    protocol_escaped = db.Column(db.String, primary_key=False)
    supplier = db.Column(db.String, primary_key=False)
    subprotocol = db.Column(db.String, primary_key=False)
    stored = db.Column(db.Boolean, primary_key=False)

    def __init__(self, data: Dict[str, any]):
        self.mla_num = data["id"]
        self.sex = data["sex"]
        self.line = data["line"]
        self.dob = data["dob"]
        self.death_date = str(data["death_date"])
        self.user = data["user"]
        self.protocol_pyrat = data["protocol_pyrat"]
        self.protocol = data["protocol"] if "protocol" in data else "---"
        self.protocol_escaped = data["protocol_escaped"] if "protocol_escaped" in data else "---"
        self.supplier = data["supplier"]
        self.subprotocol = data["subprotocol"] if "subprotocol" in data else "---"
        self.stored = data["stored"] if "stored" in data else False

    @classmethod 
    def from_json(cls, data: Dict[str, any]): 
        return cls(data)

    def to_json(self):
        return {
            "": self.mla_num,
            "sex": self.sex,
            "line": self.line,
            "dob": self.dob, 
            "death_date": self.death_date,
            "user": self.user,
            "protocol_pyrat": self.protocol_pyrat,
            "protocol": self.protocol,
            "protocol_escaped": self.protocol_escaped,
            "supplier": self.supplier,
            "subprotocol": self.subprotocol,
            "stored": self.stored
        }

    def update(self, data: Dict[str, any]): 
        self.sex = data["sex"]
        self.line = data["line"]
        self.dob = data["dob"]
        if not date_filled(self.death_date):
            self.death_date = str(data["death_date"])
        self.user = data["user"]
        self.protocol_pyrat = data["protocol_pyrat"]
        # Don't update protocol.
        self.supplier = data["supplier"]

class Note(db.Model):
    __tablename__ = "notes" 

    animal_id = db.Column(db.String, primary_key=True)
    category = db.Column(db.String, primary_key=True)
    note = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id: str, category: str, note: str):
        self.animal_id = animal_id
        self.category = category
        self.note = note

    @classmethod 
    def from_json(cls, note: Dict[str, any]): 
        return cls(note["animal_id"], note["category"], note["note"])

    def to_json(self):
        return {
            "animal_id": self.animal_id, "category": self.category, "note": self.note
        }

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

    def to_json(self): 
        return {
            "name": self.name, 
            "amount": self.amount, 
            "concentration": self.concentration,
            "days_after_surgery": self.days_after_surgery
        }

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

    def to_json(self): 
        data = {
            "name": self.name, 
            "days_after_start": self.days_after_start,
            "duration": self.duration,
        }
        if self.surgery:
            data["surgery"] = self.surgery
        return data

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
    def from_json(cls, virus: Dict[str, any]): 
        return cls(virus["name"], virus["days_after_start"], virus["amount"])

    def to_json(self): 
        return { 
            "name": self.name, 
            "days_after_start": self.days_after_start,
            "amount": self.amount
        }
    
    def update(self, virus: Dict[str, any]): 
        self.name = virus["name"] 
        self.days_after_start = virus["days_after_start"]
        self.amount = virus["amount"]

class PGeneral(db.Model):
    __tablename__ = "protocol_general"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    num_availible_animals = db.Column(db.Integer, primary_key=False) 
    allowed_users = db.Column(db.String, primary_key=False)
    suffering = db.Column(db.String, primary_key=False)

    def __init__(
        self, 
        uuid: str,
        protocol: str, 
        num_availible_animals: int, 
        allowed_users: str,
        suffering: str
    ):
        self.uuid = uuid
        self.protocol = protocol 
        self.num_availible_animals = num_availible_animals 
        self.allowed_users = allowed_users 
        self.suffering = suffering

    @classmethod 
    def from_form(cls, uuid: str, protocol: str, g: Dict[str, any]): 
        return cls(
            uuid, protocol, g["num_availible_animals"], g["allowed_users"], g["suffering"]
        )

    @classmethod 
    def from_json(cls, data: Dict[str, any]): 
        return cls.from_form(data["uuid"], data["protocol"], data)

    def to_json(self): 
        return {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "num_availible_animals": self.num_availible_animals,
            "allowed_users": self.allowed_users,
            "suffering": self.suffering
        }

    def update(self, general: Dict[str, any]): 
        self.num_availible_animals = general["num_availible_animals"]
        self.allowed_users = general["allowed_users"]
        self.suffering = general["suffering"]

class PAnesthesia(db.Model): 
    __tablename__ = "protocol_anesthesia"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    name = db.Column(db.String, primary_key=False) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

    def __init__(
        self, uuid: str, protocol: str, name: str, amount: str, concentration:str, days_after_surgery: str
    ):
        self.uuid = uuid
        self.protocol = protocol 
        self.name = name 
        self.amount = amount
        self.concentration = concentration
        self.days_after_surgery = days_after_surgery 

    @classmethod
    def from_form(cls, uuid: str, protocol: str, m: Dict[str, any]): 
        return cls(uuid, protocol, m["name"], m["amount"], m["concentration"], m["days_after_surgery"])

    @classmethod 
    def from_json(cls, m: Dict[str, any]): 
        return cls.from_form(m["uuid"], m["protocol"], m)

    def to_json(self): 
        return {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "name": self.name, 
            "amount": self.amount,
            "concentration": self.concentration,
            "days_after_surgery": self.days_after_surgery,
        }

    def update(self, medication: Dict[str, any]): 
        self.name = medication["name"] 
        self.amount = medication["amount"] 
        self.concentration = medication["concentration"] 
        self.days_after_surgery = medication["days_after_surgery"]

    def x_days_after(self): 
        return int(self.days_after_surgery)


class PAnalgesia(db.Model): 
    __tablename__ = "protocol_analgesia"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    name = db.Column(db.String, primary_key=False) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

    def __init__(
        self, uuid: str, protocol: str, name: str, amount: str, concentration:str, days_after_surgery: str
    ):
        self.uuid = uuid
        self.protocol = protocol 
        self.name = name 
        self.amount = amount
        self.concentration = concentration
        self.days_after_surgery = days_after_surgery 

    @classmethod
    def from_form(cls, uuid: str, protocol: str, m: Dict[str, any]): 
        return cls(uuid, protocol, m["name"], m["amount"], m["concentration"], m["days_after_surgery"])

    @classmethod 
    def from_json(cls, m: Dict[str, any]): 
        return cls.from_form(m["uuid"], m["protocol"], m)

    def to_json(self): 
        return {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "name": self.name, 
            "amount": self.amount,
            "concentration": self.concentration,
            "days_after_surgery": self.days_after_surgery,
        }

    def update(self, medication: Dict[str, any]): 
        self.name = medication["name"] 
        self.amount = medication["amount"] 
        self.concentration = medication["concentration"] 
        self.days_after_surgery = medication["days_after_surgery"]

    def x_days_after(self): 
        return int(self.days_after_surgery)

class PProcedure(db.Model): 
    __tablename__ = "protocol_procedures"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    name = db.Column(db.String, primary_key=False) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)
    surgery = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, uuid: str, protocol: str, name: str, days_after_start: str, duration: str, surgery: bool
    ):
        self.uuid = uuid
        self.protocol = protocol
        self.name = name 
        self.days_after_start = days_after_start 
        self.duration = duration
        self.surgery = surgery

    @classmethod
    def from_form(cls, uuid :str, protocol: str, p: Dict[str, any]): 
        surgery = AProcedure.query.get(p["name"]).surgery
        return cls(
            uuid, protocol, p["name"], p["days_after_start"], p["duration"], surgery
        )

    @classmethod 
    def from_json(cls, procedure: Dict[str, any]): 
        return cls.from_form(procedure["uuid"], procedure["protocol"], procedure)

    def to_json(self): 
        return {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "name": self.name, 
            "days_after_start": self.days_after_start,
            "duration": self.duration,
            "surgery": self.surgery
        }

    def update(self, procedure: Dict[str, any]): 
        self.name = procedure["name"] 
        self.days_after_start = procedure["days_after_start"] 
        self.duration = procedure["duration"] 
        self.surgery = AProcedure.query.get(procedure["name"]).surgery

    def x_days_after(self): 
        return int(self.days_after_start)

class PVirus(db.Model): 
    __tablename__ = "protocol_viruses"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    name = db.Column(db.String, primary_key=False) 
    days_after_start = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

    def __init__(
        self, uuid: str, protocol: str, name: str, days_after_start: str, amount: str
    ):
        self.uuid = uuid
        self.protocol = protocol
        self.name = name 
        self.days_after_start = days_after_start 
        self.amount = amount

    @classmethod
    def from_form(cls, uuid: str, protocol: str, v: Dict[str, any]): 
        return cls(uuid, protocol, v["name"], v["days_after_start"], v["amount"])

    @classmethod 
    def from_json(cls, virus: Dict[str, any]): 
        return cls.from_form(virus["uuid"], virus["protocol"], virus)

    def to_json(self): 
        return {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "name": self.name, 
            "days_after_start": self.days_after_start,
            "amount": self.amount
        }

    def update(self, p: Dict[str, any]): 
        self.name = p["name"] 
        self.days_after_start = p["days_after_start"] 
        self.amount = p["amount"] 

    def x_days_after(self): 
        return int(self.days_after_start)

class PWatercontrol(db.Model): 
    __tablename__ = "protocol_watercontrol"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    allowed = db.Column(db.Boolean, primary_key=False) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)

    def __init__(
        self, uuid: str, protocol: str, allowed: bool, days_after_start: str, duration: str
    ):
        self.uuid = uuid
        self.protocol = protocol
        self.allowed = allowed
        self.days_after_start = days_after_start 
        self.duration = duration

    @classmethod
    def from_form(cls, uuid: str, protocol: str, w: Dict[str, any]): 
        return cls(uuid, protocol, "allowed" in w, w["days_after_start"], w["duration"])

    @classmethod 
    def from_json(cls, watercontrol: Dict[str, any]): 
        return cls.from_form(watercontrol["uuid"], watercontrol["protocol"], watercontrol)

    def to_json(self): 
        data = {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "days_after_start": self.days_after_start,
            "duration": self.duration
        }
        if self.allowed: 
            data["allowed"] = self.allowed

    def update(self, watercontrol: Dict[str, any]): 
        self.allowed = "allowed" in watercontrol
        self.days_after_start = watercontrol["days_after_start"] 
        self.duration = watercontrol["duration"] 

class Protocol(db.Model): 
    __tablename__ = "protocols"

    name = db.Column(db.String, primary_key=False) 
    escaped = db.Column(db.String, primary_key=True)
    subprotocols = db.Column(db.String, primary_key=False)

    def __init__(self, name: str, escaped: str, subprotocols: str):
        self.name = name 
        self.escaped = escaped 
        self.subprotocols = subprotocols

    @classmethod
    def from_json(cls, protocol: Dict[str, any]): 
        return cls(protocol["name"], protocol["escaped"], protocol["subprotocols"])

    def to_json(self): 
        return {
            "name": self.name, "escaped": self.escaped, "subprotocols": self.subprotocols
        }

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
        
        # Add default general and watercontrol
        full_protocol = f"{self.escaped}/{subprotocol}"
        watercontrol = PWatercontrol(str(uuid.uuid4()), full_protocol, False, 0, 0)
        db.session.add(watercontrol)
        general = PGeneral(str(uuid.uuid4()), full_protocol, 10, "", "Leicht")
        db.session.add(general)
        db.session.commit()

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
    suffering = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id: str, experiment: str, watercontrol: bool, suffering: bool): 
        self.animal_id = animal_id 
        self.start = ""
        self.end = ""
        self.experiment = experiment
        self.start_weight = 0 
        self.watercontrol = watercontrol
        self.weights = json.dumps([])
        self.watercontrol_mask = json.dumps([])
        self.suffering = suffering

    @classmethod 
    def from_json(cls, general: Dict[str, any]):
        return cls(
            general["animal_id"],
            general["start"],
            general["end"],
            general["experiment"],
            general["start_weight"],
            general["watercontrol"],
            general["weights"],
            general["watercontrol_mask"],
            general["suffering"],
        )

    def to_json(self): 
        return {
            "animal_id": self.animal_id,
            "start": self.start,
            "end": self.end,
            "experiment": self.experiment,
            "start_weight": self.start_weight,
            "watercontrol": self.watercontrol,
            "weights": self.weights,
            "watercontrol_mask": self.watercontrol_mask,
            "suffering":self.suffering,
        }


class Anesthesia(db.Model): 
    __tablename__ = "anesthesia"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    toe_pinch = db.Column(db.Boolean, primary_key=False)
    days_after_surgery = db.Column(db.Integer, primary_key=False)
    protocol_entry_uuid = db.Column(db.String, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        date: str, 
        amount: str, 
        concentration: str, 
        toe_pinch: bool = True,
        days_after_surgery: int = -1,
        protocol_entry_uuid: str = ""
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
        self.protocol_entry_uuid = protocol_entry_uuid

    @classmethod
    def from_default(cls, animal_id: str, anesthesia: PAnesthesia, days_after_surgery: int):
        return cls(
            animal_id, 
            anesthesia.name, 
            str(days_after_surgery), 
            anesthesia.amount,
            anesthesia.concentration, 
            days_after_surgery=days_after_surgery,
            protocol_entry_uuid=anesthesia.uuid
        )

    @classmethod
    def from_form(cls, animal_id: str, a: Dict[str, any]):
        toe_pinch = "toe_pinch" in a
        return cls(
            animal_id, a["name"], a["date"], a["amount"], a["concentration"], toe_pinch
        )

    @classmethod 
    def from_json(cls, a: Dict[str, any]): 
        return cls.from_form(a["animal_id"], a)

    def to_json(self): 
        return {
            "animal_id": self.animal_id,
            "name": self.name, 
            "date": self.date, 
            "days_after_surgery": self.days_after_surgery, 
            "amount": self.amount, 
            "concentration": self.concentration, 
            "days_after_surgery": self.days_after_surgery,
            "toe_pinch": self.toe_pinch,
            "protocol_entry_uuid": self.protocol_entry_uuid
        }


    def update(self, a: Dict[str, any]):
        self.date = a["date"] 
        self.amount = a["amount"]
        self.concentration = a["concentration"] 
        self.toe_pinch = "toe_pinch" in a 

    def string(self): 
        return f"{self.name} ({self.concentration})"

    def set_date(self, date): 
        self.date = date


class Analgesia(db.Model): 
    __tablename__ = "analgesia"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.Integer, primary_key=False)
    protocol_entry_uuid = db.Column(db.String, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        date: str, 
        amount: str, 
        concentration: str, 
        days_after_surgery: int = -1,
        protocol_entry_uuid: str = ""
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
        self.protocol_entry_uuid = protocol_entry_uuid

    @classmethod
    def from_default(cls, animal_id: str, analgesia: PAnalgesia, days_after_surgery: int):
        return cls(
            animal_id, 
            analgesia.name, 
            str(days_after_surgery), 
            analgesia.amount, 
            analgesia.concentration, 
            days_after_surgery,
            protocol_entry_uuid=analgesia.uuid
        )

    @classmethod
    def from_form(cls, animal_id: str, a: Dict[str, any]):
        return cls(animal_id, a["name"], a["date"], a["amount"], a["concentration"])

    @classmethod 
    def from_json(cls, a: Dict[str, any]): 
        return cls.from_form(a["animal_id"], a)

    def to_json(self): 
        return {
            "animal_id": self.animal_id,
            "name": self.name, 
            "date": self.date, 
            "days_after_surgery": self.days_after_surgery, 
            "amount": self.amount, 
            "concentration": self.concentration, 
            "days_after_surgery": self.days_after_surgery,
            "protocol_entry_uuid": self.protocol_entry_uuid
        }

    def update(self, a: Dict[str, any]):
        self.date = a["date"] 
        self.amount = a["amount"]
        self.concentration = a["concentration"] 

    def string(self): 
        return f"{self.name} ({self.concentration})"

    def set_date(self, date): 
        self.date = date

class Procedure(db.Model): 
    __tablename__ = "procedures"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    start_date = db.Column(db.String, primary_key=False) 
    end_date = db.Column(db.String, primary_key=False) 
    experimenter = db.Column(db.String, primary_key=False) 
    protocol_entry_uuid = db.Column(db.String, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        start: str, 
        end: str, 
        experimenter: str,
        protocol_entry_uuid: str = ""
    ): 
        self.animal_id = animal_id 
        self.name = name 
        self.start_date = start
        self.end_date = end
        self.experimenter = experimenter
        self.protocol_entry_uuid = protocol_entry_uuid

    @classmethod 
    def from_default(cls, animal_id: str, experimenter: str, procedure: PProcedure):
        return cls(animal_id, procedure.name, "", "", experimenter, procedure.uuid)

    @classmethod 
    def from_form(cls, animal_id: str, p: Dict[str, any]): 
        return cls(animal_id, p["name"], p["start_date"], p["end_date"], p["experimenter"])

    @classmethod 
    def from_json(cls, procedure: Dict[str, any]): 
        return cls.from_form(procedure["animal_id"], procedure)

    def to_json(self): 
        return {
            "animal_id": self.animal_id,
            "name": self.name, 
            "start_date": self.start_date, 
            "end_date": self.end_date, 
            "experimenter": self.experimenter, 
            "protocol_entry_uuid": self.protocol_entry_uuid
        }

    def update(self, p: Dict[str, any]):
        self.start_date = p["start_date"]
        self.end_date = p["end_date"]
        self.experimenter = p["experimenter"]

    def set_date(self, date): 
        self.start_date = date
        self.end_date = date

 
class PostProcedure(db.Model): 
    __tablename__ = "post_procedures"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    start_date = db.Column(db.String, primary_key=False) 
    end_date = db.Column(db.String, primary_key=False) 
    experimenter = db.Column(db.String, primary_key=False) 
    protocol_entry_uuid = db.Column(db.String, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        start: str, 
        end: str, 
        experimenter: str, 
        protocol_entry_uuid: str = ""
    ): 
        self.animal_id = animal_id 
        self.name = name 
        self.start_date = start
        self.end_date = end
        self.experimenter = experimenter
        self.protocol_entry_uuid = protocol_entry_uuid

    @classmethod 
    def from_default(cls, animal_id: str, experimenter: str, procedure: PProcedure):
        return cls(animal_id, procedure.name, "", "", experimenter, procedure.uuid)
        

    @classmethod 
    def from_form(cls, animal_id: str, p: Dict[str, any]): 
        return cls(animal_id, p["name"], p["start_date"], p["end_date"], p["experimenter"])

    @classmethod 
    def from_json(cls, procedure: Dict[str, any]): 
        return cls.from_form(procedure["animal_id"], procedure)

    def to_json(self): 
        return {
            "animal_id": self.animal_id,
            "name": self.name, 
            "start_date": self.start_date, 
            "end_date": self.end_date, 
            "experimenter": self.experimenter, 
            "protocol_entry_uuid": self.protocol_entry_uuid
        }

    def update(self, p: Dict[str, any]):
        self.start_date = p["start_date"]
        self.end_date = p["end_date"]
        self.experimenter = p["experimenter"]

    def set_date(self, date): 
        self.start_date = date
        self.end_date = date

    
class Virus(db.Model): 
    __tablename__ = "virus"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)
    protocol_entry_uuid = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id, name: str, date: str, amount: str, protocol_entry_uuid: str = ""): 
        self.animal_id = animal_id 
        self.name = name
        self.date = date 
        self.amount = amount
        self.protocol_entry_uuid = protocol_entry_uuid

    @classmethod 
    def from_default(cls, animal_id: str, virus: PVirus): 
        return cls(animal_id, virus.name, "", virus.amount, virus.uuid)

    @classmethod 
    def from_form(cls, animal_id: str, virus: Dict[str, any]): 
        return cls(animal_id, virus["name"], virus["date"], virus["amount"])

    @classmethod 
    def from_json(cls, virus: Dict[str, any]): 
        return cls.from_form(virus["animal_id"], virus)

    def to_json(self): 
        return {
            "animal_id": self.animal_id,
            "name": self.name, 
            "date": self.date, 
            "amount": self.amount,
            "protocol_entry_uuid": self.protocol_entry_uuid,
        }

    def update(self, virus: Dict[str, any]):
        self.date = virus["date"]
        self.amount = virus["amount"]

    def string(self): 
        return f"{self.name}"

    def set_date(self, date): 
        self.date = date

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

ALL_TABLES = { 
  # "user": User, 
  "animal_data": AnimalData, 
  "note": Note, 
  "amedication": AMedication, 
  "aprocedure": AProcedure, 
  "avirus": AVirus, 
  "pgeneral": PGeneral,
  "panesthesia": PAnesthesia, 
  "panalgesia": PAnalgesia, 
  "pprocedure": PProcedure, 
  "pvirus": PVirus, 
  "pwatercontrol": PWatercontrol, 
  "protocol": Protocol, 
  "pgeneral": PGeneral, 
  "anesthesia": Anesthesia, 
  "analgesia": Analgesia, 
  "procedure": Procedure, 
  "post_procedure": PostProcedure, 
  "virus": Virus
}

def drop(name, Table, confirm=False): 
    if confirm:
        inp = input(f"Are you sure you want to drop table {name} (yes/no): ")
    if not confirm or inp == "yes":
        Table.__table__.drop(db.engine)
        print(f"Table {name} droped!")
    else:
        print(f"Table {name} not droped")

def drop_all(tables, confirm=False): 
    for name, Table in tables.items(): 
        drop(name, Table, confirm)

def safe_all(path): 
    backup = {} 
    for table, Table in ALL_TABLES.items(): 
        backup[table] = []
        for row in Table.query.all(): 
            backup[table].append(row.to_json())
    print(backup)
    with open(f"{path}.json", "w") as f:
        json.dump(backup, f)

def load_backup(path): 
    with open(f"{path}.json", "r") as f:
        backup = json.load(f)
    for name, data in backup.items(): 
        for row in data:
            table = ALL_TABLES[name].from_json(row)
            db.session.add(table) 
    db.session.commit()
