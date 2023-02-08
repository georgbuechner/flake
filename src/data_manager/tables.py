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
    admin = db.Column(db.Boolean, primary_key=False)
    password = db.Column(db.String, primary_key=False)
    salt = db.Column(db.String, primary_key=False)
    authenticated = db.Column(db.Boolean, default=False)

    def __init__(self, email: str, name: str, admin: bool, password: str, salt: str):
        self.email = email 
        self.name = name 
        self.admin = admin
        self.password = password 
        self.salt = salt

    @classmethod 
    def from_json(cls, user: Dict[str, any]): 
        return cls(
            user["email"], user["name"], user["admin"], user["password"], user["salt"]
        )

    def to_json(self):
        return {
            "email": self.email, 
            "name":self.name, 
            "admin":self.admin, 
            "password": self.password, 
            "salt": self.salt,
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
            "id": self.mla_num,
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
 
class AKind(db.Model): 
    __tablename__ = "availible_kinds" 

    name = db.Column(db.String, primary_key=True) 

    def __init__(self, name: str): 
        self.name = name 

    @classmethod 
    def from_json(cls, kind: Dict[str, any]): 
        print("Adding kind from json: ", kind)
        return cls(kind["name"])

    def to_json(self): 
        return {"name": self.name}

    def update(self, kind: Dict[str, any]): 
        self.name = kind["name"] 


class AMedication(db.Model): 
    __tablename__ = "availible_medication"

    name = db.Column(db.String, primary_key=True) 
    kind = db.Column(db.String, primary_key=False) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    dosis = db.Column(db.String, primary_key=False)
    procedure = db.Column(db.String, primary_key=False)
    weight_independant = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, 
        name: str, 
        kind: str, 
        amount: str, 
        concentration: str, 
        dosis: str, 
        procedure: str,
        weight_independant: bool
    ):
        self.name = name 
        self.kind = kind
        self.amount = amount 
        self.concentration = concentration 
        self.dosis = dosis
        self.procedure = procedure
        self.weight_independant = weight_independant
        self.update_amount(30)

    @classmethod 
    def from_json(cls, medication: Dict[str, any]): 
        return cls(
            medication["name"], 
            medication["kind"], 
            medication["amount"], 
            medication["concentration"], 
            medication["dosis"], 
            medication["procedure"],
            "weight_independant" in medication,
        )

    def to_json(self): 
        data = {
            "name": self.name, 
            "kind": self.kind, 
            "amount": self.amount, 
            "concentration": self.concentration,
            "dosis": self.dosis,
            "procedure": self.procedure,
        }
        if self.weight_independant: 
            data["weight_independant"] = self.weight_independant
        return data

    def update(self, medication: Dict[str, any]): 
        self.name = medication["name"] 
        self.kind = medication["kind"] 
        self.amount = medication["amount"]
        self.concentration = medication["concentration"]
        self.dosis = medication["dosis"]
        self.procedure = medication["procedure"]
        self.weight_independant = "weight_independant" in medication
        self.update_amount(30)

    def update_amount(self, weight): 
        if not self.weight_independant: 
            float_dosis = get_float(self.dosis)
            float_concentration = get_float(self.concentration) 
            self.amount = str(roundup((float_dosis*weight)/float_concentration))
            print(f"Updated amount: ({float_dosis}*{weight})/{float_concentration} = {self.amount}")


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
            uuid, protocol, 0, g["allowed_users"], g["suffering"]
        )

    @classmethod 
    def from_json(cls, data: Dict[str, any]): 
        return cls.from_form(data["uuid"], data["protocol"], data)

    def to_json(self): 
        return {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "num_availible_animals": 0,
            "allowed_users": self.allowed_users,
            "suffering": self.suffering
        }

    def update(self, general: Dict[str, any]): 
        self.num_availible_animals = 0
        self.allowed_users = general["allowed_users"]
        self.suffering = general["suffering"]

class PAllowedMice(db.Model):
    __tablename__ = "protocol_allowed_mice"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    name = db.Column(db.Integer, primary_key=False) 
    num_availible_animals = db.Column(db.Integer, primary_key=False) 

    def __init__(
        self, 
        uuid: str,
        protocol: str, 
        name: str,
        num_availible_animals: int, 
    ):
        self.uuid = uuid
        self.protocol = protocol 
        self.name = name
        self.num_availible_animals = num_availible_animals 

    @classmethod 
    def from_form(cls, uuid: str, protocol: str, g: Dict[str, any]): 
        return cls(uuid, protocol, g["name"], g["num_availible_animals"])

    @classmethod 
    def from_json(cls, data: Dict[str, any]): 
        return cls.from_form(data["uuid"], data["protocol"], data)

    def to_json(self): 
        return {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "name": self.name,
            "num_availible_animals": self.num_availible_animals,
        }

    def update(self, general: Dict[str, any]): 
        self.name = general["name"]
        self.num_availible_animals = general["num_availible_animals"]


class PMedication(db.Model): 
    __tablename__ = "protocol_medication"

    uuid = db.Column(db.String, primary_key=True)
    protocol = db.Column(db.String, primary_key=False) 
    name = db.Column(db.String, primary_key=False) 
    kind = db.Column(db.String, primary_key=False) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    dosis = db.Column(db.String, primary_key=False)
    procedure = db.Column(db.String, primary_key=False)
    weight_independant = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, 
        uuid: str, 
        protocol: str, 
        name: str, 
        kind: str, 
        procedure: str,
        amount: str, 
        concentration: str, 
        dosis: str, 
        weight_independant: bool
    ):
        self.uuid = uuid
        self.protocol = protocol 
        self.name = name 
        self.kind= kind
        self.procedure = procedure 
        self.amount = amount
        self.concentration = concentration
        self.dosis = dosis
        self.weight_independant = weight_independant
        self.update_amount(30)

    @classmethod
    def from_form(cls, uuid: str, protocol: str, medication: Dict[str, any]): 
        return cls(
            uuid, 
            protocol, 
            medication["name"], 
            medication["kind"], 
            medication["procedure"],
            medication["amount"], 
            medication["concentration"], 
            medication["dosis"], 
            "weight_independant" in medication
        )

    @classmethod 
    def from_json(cls, medication: Dict[str, any]): 
        return cls.from_form(medication["uuid"], medication["protocol"], medication)

    def to_json(self): 
        data = {
            "uuid": self.uuid, 
            "protocol": self.protocol,
            "name": self.name, 
            "kind": self.kind, 
            "procedure": self.procedure,
            "amount": self.amount,
            "concentration": self.dosis,
            "dosis": self.dosis,
        }        
        if self.weight_independant: 
            data["weight_independant"] = self.weight_independant
        return data


    def update(self, medication: Dict[str, any]): 
        self.name = medication["name"] 
        self.kind = medication["kind"] 
        self.amount = medication["amount"] 
        self.concentration = medication["concentration"] 
        self.dosis = medication["dosis"] 
        self.procedure = medication["procedure"]
        self.weight_independant = "weight_independant" in medication
        self.update_amount(30)

    def update_amount(self, weight): 
        if not self.weight_independant: 
            float_dosis = get_float(self.dosis) 
            float_concentration = get_float(self.concentration)
            self.amount = str(roundup((float_dosis*weight)/float_concentration))


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
        return

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


class Medication(db.Model): 
    __tablename__ = "medication"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    kind = db.Column(db.String, primary_key=False) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    dosis = db.Column(db.String, primary_key=False)
    weight_independant = db.Column(db.Boolean, primary_key=False)
    toe_pinch = db.Column(db.Boolean, primary_key=False)
    procedure = db.Column(db.Integer, primary_key=True)
    protocol_entry_uuid = db.Column(db.String, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        kind: str, 
        procedure: str,
        amount: str, 
        concentration: str, 
        dosis: str, 
        weight_independant: bool,
        toe_pinch: bool = True,
        protocol_entry_uuid: str = ""
    ):
        """! Initializes Medication. 

        Uses `procedure` as a placeholder for date, to ensure uniqueness (since
        medication might be added multiple days. Later the dates will be
        succesive dates. 
        """
        self.animal_id = animal_id 
        self.name = name 
        self.kind = kind
        self.procedure = procedure
        self.amount = amount 
        self.concentration = concentration 
        self.dosis = dosis
        self.weight_independant = weight_independant
        self.toe_pinch = toe_pinch
        self.protocol_entry_uuid = protocol_entry_uuid
        self.update_amount(30)

    @classmethod
    def from_default(cls, animal_id: str, medication: PMedication):
        return cls(
            animal_id, 
            medication.name, 
            medication.kind, 
            medication.procedure,
            medication.amount,
            medication.concentration, 
            medication.dosis, 
            medication.weight_independant, 
            protocol_entry_uuid=medication.uuid
        )

    @classmethod
    def from_form(cls, animal_id: str, medication: Dict[str, any]):
        toe_pinch = "toe_pinch" in medication
        return cls(
            animal_id, 
            medication["name"], 
            medication["kind"], 
            medication["procedure"], 
            medication["amount"], 
            medication["concentration"], 
            medication["dosis"], 
            "weight_independant" in medication,
            toe_pinch=toe_pinch
        )

    @classmethod 
    def from_json(cls, medication: Dict[str, any]): 
        return cls.from_form(medication["animal_id"], medication)

    def to_json(self): 
        data = {
            "animal_id": self.animal_id,
            "name": self.name, 
            "kind": self.kind, 
            "procedure": self.procedure,
            "amount": self.amount, 
            "concentration": self.concentration, 
            "dosis": self.dosis, 
            "toe_pinch": self.toe_pinch,
            "protocol_entry_uuid": self.protocol_entry_uuid
        }
        if self.weight_independant: 
            data["weight_independant"] = self.weight_independant
        return data

    def update(self, medication: Dict[str, any]):
        self.kind = medication["kind"] 
        self.procedure = medication["procedure"]
        self.amount = medication["amount"]
        self.concentration = medication["concentration"] 
        self.dosis = medication["dosis"] 
        self.weight_independant = "weight_independant" in medication
        self.toe_pinch = "toe_pinch" in medication 
        self.update_amount(30)

    def string(self): 
        return f"{self.name} ({self.concentration} mg/ml)"

    def set_date(self, date): 
        self.date = date

    def update_amount(self, weight): 
        if not self.weight_independant: 
            float_dosis = get_float(self.dosis)
            float_concentration = get_float(self.concentration)
            self.amount = str(roundup((float_dosis*weight)/float_concentration))

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
    if not isinstance(table, str):
        return {k:v for (k,v) in table.__dict__.items() if k[0] != "_"}
    return table


EXPERIMENT_TABLES = {
    "medication": Medication, 
    "procedures": Procedure,
    "post_procedures": PostProcedure,
    "viruses": Virus 
}
EXPERIMENT_TABLES_REDUCED = {
    "medication": Medication, 
    "procedures": Procedure,
    "post_procedures": PostProcedure,
    "viruses": Virus 
}

PROTOCOL_TABLES = {
    "medication": PMedication, 
    "allowed_animals": PAllowedMice, 
    "procedures": PProcedure, 
    "viruses": PVirus
}

DEFINITION_TABLES = { 
    "kinds": AKind, 
    "medication": AMedication, 
    "procedures": AProcedure, 
    "viruses": AVirus
}

ALL_TABLES = { 
  # "user": User, 
  "animal_data": AnimalData, 
  "note": Note, 
  "akinds": AKind, 
  "amedication": AMedication, 
  "aprocedure": AProcedure, 
  "avirus": AVirus, 
  "pgeneral": PGeneral,
  "pmedication": PMedication, 
  "pprocedure": PProcedure, 
  "pvirus": PVirus, 
  "pwatercontrol": PWatercontrol, 
  "protocol": Protocol, 
  "pgeneral": PGeneral, 
  "medication": Medication, 
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

def safe(path, name, Table): 
    backup = {name: []} 
    for row in Table.query.all(): 
        backup[name].append(row.to_json())
    with open(f"{path}.json", "w") as f:
        json.dump(backup, f)

def safe_all(path): 
    backup = {} 
    for table, Table in ALL_TABLES.items(): 
        backup[table] = []
        for row in Table.query.all(): 
            backup[table].append(row.to_json())
    with open(f"{path}.json", "w") as f:
        json.dump(backup, f)

def load_backup(path): 
    with open(f"{path}.json", "r") as f:
        backup = json.load(f)
    for name, data in backup.items(): 
        for row in data:
            try: 
                table = ALL_TABLES[name].from_json(row)
            except Exception as err: 
                print("While adding row: ", row)
                print(repr(err))
                exit()
            db.session.add(table) 
        try: 
            db.session.commit()
        except Exception as err:
            print("While commiting table: ", name)
            print(repr(err))
            exit()


def roundup(x): 
    x = int(math.ceil(x / 10.0)) * 10
    return x

def get_float(text: str) -> float: 
    for delimiter in ["-", "/"]:
        if delimiter in text:
            # works for both: '12/14'->12.0 and '14'->12.0
            float_text = float(text.split(delimiter)[0])  
            return float_text
    try: 
        return float(text)
    except:
        return -1
