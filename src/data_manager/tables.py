import json
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

class AMedication(db.Model): 
    __tablename__ = "availible_medication"

    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

class AProcedure(db.Model): 
    __tablename__ = "availible_procedures"

    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)
    surgery = db.Column(db.Boolean, primary_key=False)

class AVirus(db.Model): 
    __tablename__ = "availible_viruses"

    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

class PAnesthesia(db.Model): 
    __tablename__ = "protocol_anesthesia"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

class PAnalgesia(db.Model): 
    __tablename__ = "protocol_analgesia"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)


class PProcedure(db.Model): 
    __tablename__ = "protocol_procedures"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)
    surgery = db.Column(db.Boolean, primary_key=False)

class PVirus(db.Model): 
    __tablename__ = "protocol_viruses"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

class PWatercontrol(db.Model): 
    __tablename__ = "protocol_watercontrol"

    protocol = db.Column(db.String, primary_key=True) 
    allowed = db.Column(db.Boolean, primary_key=False) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)

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

    def __init__(self, animal_id: str, experiment: str, watercontrol: bool): 
        self.animal_id = animal_id 
        self.start = ""
        self.end = ""
        self.experiment = experiment
        self.start_weight = 0 
        self.watercontrol = watercontrol
        self.weights = json.dumps([])

class Anesthesia(db.Model): 
    __tablename__ = "anesthesia"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    toe_pinch = db.Column(db.Boolean, primary_key=False)
    days_after_surgery = db.Column(db.Boolean, primary_key=False)

    def __init__(self, animal_id: str, anesthesia: PAnesthesia, days_after_surgery: int): 
        """! Initializes Anesthesia. 

        Uses days_after_surgery as a placeholder for date, to ensure uniqueness (since
        anesthetic might be added at multiple days. Later the dates will be
        succesive dates.

        @param animal_id  ID of animal.
        @param anesthesia  The default entry from PAnesthesia.
        @param num  Placeholder for date, to ensure uniqueness (=days-after-surgery)
        """
        self.animal_id = animal_id 
        self.name = anesthesia.name 
        self.date = str(days_after_surgery) 
        self.amount = anesthesia.amount 
        self.concentration = anesthesia.concentration 
        self.toe_pinch = True
        self.days_after_surgery = days_after_surgery

class Analgesia(db.Model): 
    __tablename__ = "analgesia"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.Integer, primary_key=False)


    def __init__(self, animal_id: str, analgesia: PAnesthesia, days_after_surgery: int):
        """! Initializes Analgesia. 

        Uses num as a placeholder for date, to ensure uniqueness (since
        analgesia might be added multiple days. Later the dates will be
        succesive dates. 

        @param animal_id  ID of animal.
        @param analgesia  The default entry from PAnesthesia.
        @param num  Placeholder for date, to ensure uniqueness.
        """
        self.animal_id = animal_id 
        self.name = analgesia.name 
        self.date = str(days_after_surgery) 
        self.amount = analgesia.amount 
        self.concentration = analgesia.concentration 
        self.days_after_surgery = days_after_surgery

class Procedure(db.Model): 
    __tablename__ = "procedures"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    start_date = db.Column(db.String, primary_key=False) 
    end_date = db.Column(db.String, primary_key=False) 
    experimenter = db.Column(db.String, primary_key=False) 

    def __init__(self, animal_id: str, experimenter: str, procedure: PProcedure): 
        self.animal_id = animal_id 
        self.name = procedure.name 
        self.start_date = ""
        self.end_date = ""
        self.experimenter = experimenter

class PostProcedure(db.Model): 
    __tablename__ = "post_procedures"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    start_date = db.Column(db.String, primary_key=False) 
    end_date = db.Column(db.String, primary_key=False) 
    experimenter = db.Column(db.String, primary_key=False) 

    def __init__(self, animal_id: str, experimenter: str, procedure: PProcedure): 
        self.animal_id = animal_id 
        self.name = procedure.name 
        self.start_date = ""
        self.end_date = ""
        self.experimenter = experimenter

class Virus(db.Model): 
    __tablename__ = "virus"

    animal_id = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    date = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id, virus: PVirus): 
        self.animal_id = animal_id 
        self.name = virus.name 
        self.date = ""
        self.amount = virus.amount

def table_to_json(table): 
    """! Removes fields added by sql-alchamy. """
    return {k:v for (k,v) in table.__dict__.items() if k[0] != "_"}
