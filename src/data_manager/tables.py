from __future__ import annotations

import json
import math
import uuid
import random
import re
from exceptions.exceptions import EntryNotFound, FlakeError, InvalidDateException, InvalidTypeException
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.model import Model
from sqlalchemy.orm import Mapped, validates
from typing import Any, Callable, Dict, List, Mapping, Tuple, TypeVar, TYPE_CHECKING, overload
from types import SimpleNamespace
from utils.dt_utils import date_filled, unify_date, daterange_str

db = SQLAlchemy()
T = TypeVar("T")


def optional_text(value: object) -> str | None:
    """Use NULL for unset schedule values, preserving range notation."""
    if value is None or (isinstance(value, str) and value.strip() in ("", "-", "--", "---")):
        return None
    return str(value)


def optional_integer(value: object, field: str, non_negative: bool = False) -> int | None:
    text = optional_text(value)
    if text is None:
        return None
    if type(value) is not int and not (isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", text.strip())):
        raise InvalidTypeException(f"{field} must be an integer or left blank.")
    number = int(text)
    if not -(2**63) <= number < 2**63 or (non_negative and number < 0):
        raise InvalidTypeException(f"Invalid integer for {field}: {value}")
    return number


class User(db.Model):
    """!An admin user capable of viewing reports.

    @param email  Email address of user
    @param name  Name of user 
    @param password  Hashed password of user 
    @param sal  Salt matching password-hash.
    @param password  Encrypted password for the user

    """
    __tablename__ = 'user'

    email: Mapped[str] = db.Column(db.String, primary_key=True)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    admin: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    password: Mapped[str | bytes] = db.Column(db.String, primary_key=False)
    salt: Mapped[bytes] = db.Column(db.String, primary_key=False)
    authenticated: Mapped[bool] = db.Column(db.Boolean, default=False)

    def __init__(self, email: str, name: str, admin: bool, password: str | bytes, salt: bytes) -> None:
        self.email = email 
        self.name = name 
        self.admin = admin
        self.password = password 
        self.salt = salt

    @classmethod 
    def from_json(cls, user: Mapping[str, Any]) -> User:
        return cls(
            user["email"], user["name"], user["admin"], user["password"], user["salt"]
        )

    def is_active(self) -> bool:
        """! True, as all users are active."""
        return True

    def get_id(self) -> str:
        """! Return the email address to satisfy Flask-Login's requirements."""
        return self.email

    def is_authenticated(self) -> bool:
        """! Return True if the user is authenticated."""
        return self.authenticated

    def is_anonymous(self) -> bool:
        """! False, as anonymous users aren't supported."""
        return False

class VerificationCode(db.Model): 
    __tablename__ = "verification_codes" 

    priv: Mapped[str] = db.Column(db.String, primary_key=True)
    pub: Mapped[str] = db.Column(db.String, primary_key=True)
    email: Mapped[str] = db.Column(db.String, primary_key=False)

    if TYPE_CHECKING:
        def __init__(self, *, priv: str, pub: str, email: str) -> None: ...

class AnimalData(db.Model): 
    __tablename__ = "animal_data" 

    mla_num: Mapped[str] = db.Column(db.String, primary_key=True)
    sex: Mapped[str] = db.Column(db.String, primary_key=False)
    line: Mapped[str] = db.Column(db.String, primary_key=False)
    dob: Mapped[str] = db.Column(db.String, primary_key=False)
    death_date: Mapped[str | None] = db.Column(db.String, primary_key=False)
    user: Mapped[str] = db.Column(db.String, primary_key=False)
    protocol_pyrat: Mapped[str] = db.Column(db.String, primary_key=False)
    protocol: Mapped[str] = db.Column(db.String, primary_key=False)
    protocol_escaped: Mapped[str] = db.Column(db.String, primary_key=False)
    supplier: Mapped[str] = db.Column(db.String, primary_key=False)
    subprotocol: Mapped[str] = db.Column(db.String, primary_key=False)
    stored: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    procedures_after_death: Mapped[int | None] = db.Column(db.Integer, primary_key=False)
    missing_sacrifice: Mapped[bool | None] = db.Column(db.Boolean, primary_key=False)

    def __init__(self, data: Mapping[str, Any]) -> None:
        self.mla_num = data["id"]
        self.sex = data["sex"]
        self.line = data["line"]
        self.dob = unify_date(data["dob"])
        self.death_date = unify_date(str(data["death_date"]))
        self.user = data["user"]
        self.protocol_pyrat = data["protocol_pyrat"]
        self.protocol = data["protocol"] if "protocol" in data else "---"
        self.protocol_escaped = data["protocol_escaped"] if "protocol_escaped" in data else "---"
        self.supplier = data["supplier"]
        self.subprotocol = data["subprotocol"] if "subprotocol" in data else "---"
        self.stored = data["stored"] if "stored" in data else False

    @classmethod 
    def from_json(cls, data: Mapping[str, Any]) -> AnimalData:
        return cls(data)

    def update(self, data: Mapping[str, Any]) -> None:
        self.sex = data["sex"]
        self.line = data["line"]
        self.dob = unify_date(data["dob"])
        if not date_filled(self.death_date):
            self.death_date = unify_date(str(data["death_date"]))
        self.user = data["user"]
        self.protocol_pyrat = data["protocol_pyrat"]
        # Don't update protocol.
        self.supplier = data["supplier"]

class CommentBackup(db.Model): 
    __tablename__ = "comment_backup" 

    animal_id: Mapped[str] = db.Column(db.String, primary_key=True)
    comment: Mapped[str] = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id: str, comment: str) -> None:
        self.animal_id = animal_id
        self.comment = comment

    def update(self, comment: str) -> None:
        self.comment = comment

class CommentData(): 
    def __init__(self, comment: str) -> None:
        start, end, start_weight = parse_comment(comment) 
        self.start_date = start
        self.end_date = end
        self.start_weight = start_weight

class Note(db.Model):
    __tablename__ = "notes" 

    animal_id: Mapped[str] = db.Column(db.String, primary_key=True)
    category: Mapped[str] = db.Column(db.String, primary_key=True)
    note: Mapped[str] = db.Column(db.String, primary_key=False)
    surgery_sheet: Mapped[bool] = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, animal_id: str, category: str, surgery_sheet: bool, note: str
    ) -> None:
        self.animal_id = animal_id
        self.category = category
        self.note = note
        self.surgery_sheet = surgery_sheet

    @classmethod 
    def from_json(cls, note: Mapping[str, Any]) -> Note:
        return cls(note["animal_id"], note["category"], note["surgery_sheet"], note["note"]) 

    def update(self, note: str, surgery_sheet: bool) -> None:
        self.note = note
        self.surgery_sheet = surgery_sheet
 
class AKind(db.Model): 
    __tablename__ = "availible_kinds" 

    name: Mapped[str] = db.Column(db.String, primary_key=True)

    def __init__(self, name: str) -> None:
        self.name = name 

    @classmethod 
    def from_json(cls, kind: Mapping[str, Any]) -> AKind:
        return cls(kind["name"])

    def update(self, kind: Mapping[str, Any]) -> None:
        self.name = kind["name"] 

class ALine(db.Model): 
    __tablename__ = "availible_lines" 

    name: Mapped[str] = db.Column(db.String, primary_key=True)

    def __init__(self, name: str) -> None:
        self.name = name 

    @classmethod 
    def from_json(cls, line: Mapping[str, Any]) -> ALine:
        return cls(line["name"])

    def update(self, line: Mapping[str, Any]) -> None:
        self.name = line["name"] 


class AMedication(db.Model): 
    __tablename__ = "availible_medication"

    name: Mapped[str] = db.Column(db.String, primary_key=True)
    kind: Mapped[str] = db.Column(db.String, primary_key=False)
    amount: Mapped[str] = db.Column(db.String, primary_key=False)
    concentration: Mapped[str] = db.Column(db.String, primary_key=False)
    dosis: Mapped[str] = db.Column(db.String, primary_key=False)
    procedure: Mapped[str] = db.Column(db.String, primary_key=False)
    weight_independant: Mapped[bool] = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, 
        name: str, 
        kind: str, 
        amount: str, 
        concentration: str, 
        dosis: str, 
        procedure: str,
        weight_independant: bool
    ) -> None:
        self.name = name 
        self.kind = kind
        self.amount = amount 
        self.concentration = concentration 
        self.dosis = dosis
        self.procedure = procedure
        self.weight_independant = weight_independant
        self.update_amount(30)

    @classmethod 
    def from_json(cls, medication: Mapping[str, Any]) -> AMedication:
        return cls(
            medication["name"], 
            medication["kind"], 
            medication["amount"], 
            medication["concentration"], 
            medication["dosis"], 
            medication["procedure"],
            "weight_independant" in medication,
        )

    def update(self, medication: Mapping[str, Any]) -> None:
        self.name = medication["name"] 
        self.kind = medication["kind"] 
        self.amount = medication["amount"]
        self.concentration = medication["concentration"]
        self.dosis = medication["dosis"]
        self.procedure = medication["procedure"]
        self.weight_independant = "weight_independant" in medication
        self.update_amount(30)

    def update_amount(self, weight: float) -> None:
        if not self.weight_independant: 
            float_dosis = get_float(self.dosis)
            float_concentration = get_float(self.concentration) 
            if float_concentration <= 0:
                raise InvalidTypeException("Medication concentration must be greater than zero")
            self.amount = str(roundup((float_dosis*weight)/float_concentration))
            print(f"Updated amount: ({float_dosis}*{weight})/{float_concentration} = {self.amount}")


class AProcedure(db.Model): 
    __tablename__ = "availible_procedures"

    name: Mapped[str] = db.Column(db.String, primary_key=True)
    days_after_start: Mapped[int | None] = db.Column(db.Integer, primary_key=False)
    duration: Mapped[str | None] = db.Column(db.String, primary_key=False)
    surgery: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    requires_medication: Mapped[int | None] = db.Column(db.Integer, primary_key=False)
    requires_virus: Mapped[int | None] = db.Column(db.Integer, primary_key=False)

    @validates("days_after_start", "requires_medication", "requires_virus")
    def validate_integer(self, key: str, value: object) -> int | None:
        return optional_integer(value, key, non_negative=key != "days_after_start")

    @validates("duration")
    def validate_duration(self, key: str, value: object) -> str | None:
        return optional_text(value)

    def __init__(
        self, 
        name: str, 
        days_after_start: int | str | None,
        duration: str | None,
        surgery: bool,
        requires_medication: int | str | None,
        requires_virus: int | str | None
    ) -> None:
        self.name = name 
        self.days_after_start = optional_integer(days_after_start, "days_after_start")
        self.duration = duration 
        self.surgery = surgery
        self.requires_medication = optional_integer(requires_medication, "requires_medication", non_negative=True)
        self.requires_virus = optional_integer(requires_virus, "requires_virus", non_negative=True)

    @classmethod
    def from_json(cls, procedure: Mapping[str, Any]) -> AProcedure:
        return cls(
            procedure["name"], 
            procedure["days_after_start"], 
            procedure["duration"], 
            "surgery" in procedure,
            procedure["requires_medication"], 
            procedure["requires_virus"], 
        )

    def update(self, procedure: Mapping[str, Any]) -> None:
        self.name = procedure["name"] 
        self.days_after_start = procedure["days_after_start"] 
        self.duration = procedure["duration"] 
        self.surgery = "surgery" in procedure
        self.requires_medication = procedure["requires_medication"] 
        self.requires_virus = procedure["requires_virus"] 

class AVirus(db.Model): 
    __tablename__ = "availible_viruses"

    name: Mapped[str] = db.Column(db.String, primary_key=True)
    procedure: Mapped[str] = db.Column(db.String, primary_key=False)
    amount: Mapped[str] = db.Column(db.String, primary_key=False)

    def __init__(self, name: str, procedure: str, amount: str) -> None:
        self.name = name 
        self.procedure = procedure 
        self.amount = amount

    @classmethod 
    def from_json(cls, virus: Mapping[str, Any]) -> AVirus:
        return cls(virus["name"], virus["procedure"], virus["amount"])

   
    def update(self, virus: Mapping[str, Any]) -> None:
        self.name = virus["name"] 
        self.procedure = virus["procedure"]
        self.amount = virus["amount"]

class PGeneral(db.Model):
    __tablename__ = "protocol_general"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    protocol: Mapped[str] = db.Column(db.String, primary_key=False, unique=True)
    num_availible_animals: Mapped[int] = db.Column(db.Integer, primary_key=False)
    allowed_users: Mapped[str] = db.Column(db.String, primary_key=False)
    suffering: Mapped[str] = db.Column(db.String, primary_key=False)

    def __init__(
        self, protocol: str, num_availible_animals: int, allowed_users: str, suffering: str
    ) -> None:
        self.uuid = str(uuid.uuid4())
        self.protocol = protocol 
        self.num_availible_animals = num_availible_animals 
        self.allowed_users = allowed_users 
        self.suffering = suffering

    @classmethod 
    def from_form(cls, protocol: str, g: Mapping[str, Any]) -> PGeneral:
        return cls(protocol, 0, g["allowed_users"], g["suffering"])

    @classmethod 
    def from_json(cls, data: Mapping[str, Any]) -> PGeneral:
        return cls.from_form(data["protocol"], data)

    def update(self, general: Mapping[str, Any]) -> None:
        self.num_availible_animals = 0
        self.allowed_users = general["allowed_users"]
        self.suffering = general["suffering"]

class PAllowedMice(db.Model):
    __tablename__ = "protocol_allowed_mice"
    __table_args__ = (
        db.UniqueConstraint("protocol", "name", name="uq_protocol_allowed_mice_protocol_name"),
        db.CheckConstraint(
            "num_availible_animals IS NULL OR "
            "(typeof(num_availible_animals) = 'integer' AND num_availible_animals >= 0)",
            name="ck_protocol_allowed_mice_allowance",
        ),
    )

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    protocol: Mapped[str] = db.Column(db.String, primary_key=False)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    num_availible_animals: Mapped[int | None] = db.Column(db.Integer, primary_key=False)

    @validates("num_availible_animals")
    def validate_num_availible_animals(self, key: str, value: object) -> int | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
            value = int(value.strip())
        if type(value) is not int or value < 0:
            raise InvalidTypeException(
                "Number of allowed animals must be a non-negative integer or left blank."
            )
        return value

    def __init__(
        self, protocol: str, name: str, num_availible_animals: int | str | None,
    ) -> None:
        self.uuid = str(uuid.uuid4())
        self.protocol = protocol 
        self.name = name
        self.num_availible_animals = self.validate_num_availible_animals("num_availible_animals", num_availible_animals)

    @classmethod 
    def from_form(cls, protocol: str, g: Mapping[str, Any]) -> PAllowedMice:
        return cls(protocol, g["name"], g["num_availible_animals"])

    @classmethod 
    def from_json(cls, data: Mapping[str, Any]) -> PAllowedMice:
        return cls.from_form(data["protocol"], data)

    def update(self, general: Mapping[str, Any]) -> None:
        self.name = general["name"]
        self.num_availible_animals = general["num_availible_animals"]


class PMedication(db.Model): 
    __tablename__ = "protocol_medication"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    protocol: Mapped[str] = db.Column(db.String, primary_key=False)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    kind: Mapped[str] = db.Column(db.String, primary_key=False)
    amount: Mapped[str] = db.Column(db.String, primary_key=False)
    concentration: Mapped[str] = db.Column(db.String, primary_key=False)
    dosis: Mapped[str] = db.Column(db.String, primary_key=False)
    procedure: Mapped[str] = db.Column(db.String, primary_key=False)
    weight_independant: Mapped[bool] = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, 
        protocol: str, 
        name: str, 
        kind: str, 
        procedure: str,
        amount: str, 
        concentration: str, 
        dosis: str, 
        weight_independant: bool
    ) -> None:
        self.uuid = str(uuid.uuid4())
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
    def from_form(cls, protocol: str, medication: Mapping[str, Any]) -> PMedication:
        return cls(
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
    def from_json(cls, medication: Mapping[str, Any]) -> PMedication:
        return cls.from_form(medication["protocol"], medication)

    def update(self, medication: Mapping[str, Any]) -> None:
        self.name = medication["name"] 
        self.kind = medication["kind"] 
        self.amount = medication["amount"] 
        self.concentration = medication["concentration"] 
        self.dosis = medication["dosis"] 
        self.procedure = medication["procedure"]
        self.weight_independant = "weight_independant" in medication
        self.update_amount(30)

    def update_amount(self, weight: float) -> None:
        if not self.weight_independant: 
            float_dosis = get_float(self.dosis) 
            float_concentration = get_float(self.concentration)
            if float_concentration <= 0:
                raise InvalidTypeException("Medication concentration must be greater than zero")
            self.amount = str(roundup((float_dosis*weight)/float_concentration))


class PProcedure(db.Model): 
    __tablename__ = "protocol_procedures"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    protocol: Mapped[str] = db.Column(db.String, primary_key=False)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    # Legacy offset ranges are retained; automatic scheduling still needs a scalar.
    days_after_start: Mapped[str | None] = db.Column(db.String, primary_key=False)
    duration: Mapped[str | None] = db.Column(db.String, primary_key=False)
    surgery: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    optional: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    requires_medication: Mapped[int | None] = db.Column(db.Integer, primary_key=False)
    requires_virus: Mapped[int | None] = db.Column(db.Integer, primary_key=False)

    @validates("days_after_start", "duration")
    def validate_schedule(self, key: str, value: object) -> str | None:
        return optional_text(value)

    @validates("requires_medication", "requires_virus")
    def validate_count(self, key: str, value: object) -> int | None:
        return optional_integer(value, key, non_negative=True)

    def __init__(
        self, 
        protocol: str, 
        name: str, 
        days_after_start: str | int | None,
        duration: str | int | None,
        surgery: bool, 
        optional: bool,
        requires_medication: int | str | None,
        requires_virus: int | str | None
    ) -> None:
        self.uuid = str(uuid.uuid4())
        self.protocol = protocol
        self.name = name 
        self.days_after_start = optional_text(days_after_start)
        self.duration = optional_text(duration)
        self.surgery = surgery
        self.optional = optional
        self.requires_medication = optional_integer(requires_medication, "requires_medication", non_negative=True)
        self.requires_virus = optional_integer(requires_virus, "requires_virus", non_negative=True)

    @classmethod
    def from_form(cls, protocol: str, procedure: Mapping[str, Any]) -> PProcedure:
        definition = db.session.get(AProcedure, procedure["name"])
        if definition is None:
            raise EntryNotFound(f"Procedure {procedure['name']} not found")
        surgery = definition.surgery
        optional = "optional" in procedure
        return cls(
            protocol, 
            procedure["name"], 
            procedure["days_after_start"], 
            procedure["duration"], 
            surgery, 
            optional,
            procedure["requires_medication"], 
            procedure["requires_virus"], 
        )

    @classmethod 
    def from_json(cls, procedure: Mapping[str, Any]) -> PProcedure:
        return cls.from_form(procedure["protocol"], procedure)

    def update(self, procedure: Mapping[str, Any]) -> None:
        self.name = procedure["name"] 
        self.days_after_start = procedure["days_after_start"] 
        self.duration = procedure["duration"] 
        definition = db.session.get(AProcedure, procedure["name"])
        if definition is None:
            raise EntryNotFound(f"Procedure {procedure['name']} not found")
        self.surgery = definition.surgery
        self.optional = "optional" in procedure
        self.requires_medication = procedure["requires_medication"] 
        self.requires_virus = procedure["requires_virus"] 

    def get_duration(self) -> int: 
        """ Gets duration or random duration between min and max """
        try:
            if isinstance(self.duration, str):
                min_max = self.duration.split("-")
                if len(min_max) == 2:
                    return random.randint(int(min_max[0]), int(min_max[1]))
                if len(min_max) == 1:
                    return int(min_max[0])
            elif isinstance(self.duration, int):
                return self.duration
        except ValueError as error:
            raise InvalidTypeException(f"Invalid duration: {self.duration}!") from error
        raise InvalidTypeException(f"Invalid duration: {self.duration}!")

class PVirus(db.Model): 
    __tablename__ = "protocol_viruses"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    protocol: Mapped[str] = db.Column(db.String, primary_key=False)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    procedure: Mapped[str] = db.Column(db.String, primary_key=False)
    amount: Mapped[str] = db.Column(db.String, primary_key=False)
    optional: Mapped[bool] = db.Column(db.Boolean, primary_key=False)

    def __init__(
        self, protocol: str, name: str, procedure: str, amount: str, optional: bool
    ) -> None:
        self.uuid = str(uuid.uuid4())
        self.protocol = protocol
        self.name = name 
        self.procedure = procedure 
        self.amount = amount
        self.optional = optional

    @classmethod
    def from_form(cls, protocol: str, v: Mapping[str, Any]) -> PVirus:
        optional = "optional" in v
        return cls(protocol, v["name"], v["procedure"], v["amount"], optional)

    @classmethod 
    def from_json(cls, virus: Mapping[str, Any]) -> PVirus:
        return cls.from_form(virus["protocol"], virus)

    def update(self, v: Mapping[str, Any]) -> None:
        self.name = v["name"] 
        self.procedure = v["procedure"] 
        self.amount = v["amount"] 
        self.optional = "optional" in v

class PWatercontrol(db.Model): 
    __tablename__ = "protocol_watercontrol"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    protocol: Mapped[str] = db.Column(db.String, primary_key=False, unique=True)
    allowed: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    # Preserve legacy ranges without choosing a start or duration for the user.
    days_after_start: Mapped[str | None] = db.Column(db.String, primary_key=False)
    duration: Mapped[str | None] = db.Column(db.String, primary_key=False)

    @validates("days_after_start", "duration")
    def validate_schedule(self, key: str, value: object) -> str | None:
        return optional_text(value)

    def __init__(
        self, protocol: str, allowed: bool, days_after_start: str | int | None, duration: str | int | None
    ) -> None:
        self.uuid = str(uuid.uuid4())
        self.protocol = protocol
        self.allowed = allowed
        self.days_after_start = optional_text(days_after_start)
        self.duration = optional_text(duration)

    @classmethod
    def from_form(cls, protocol: str, w: Mapping[str, Any]) -> PWatercontrol:
        return cls(protocol, "allowed" in w, w["days_after_start"], w["duration"])

    @classmethod 
    def from_json(cls, watercontrol: Mapping[str, Any]) -> PWatercontrol:
        return cls.from_form(watercontrol["protocol"], watercontrol)

    def update(self, watercontrol: Mapping[str, Any]) -> None:
        self.allowed = "allowed" in watercontrol
        self.days_after_start = watercontrol["days_after_start"] 
        self.duration = watercontrol["duration"] 

class Protocol(db.Model): 
    __tablename__ = "protocols"

    name: Mapped[str] = db.Column(db.String, primary_key=False)
    escaped: Mapped[str] = db.Column(db.String, primary_key=True)
    subprotocols: Mapped[str] = db.Column(db.String, primary_key=False)

    def __init__(self, name: str, escaped: str, subprotocols: str) -> None:
        self.name = name 
        self.escaped = escaped 
        self.subprotocols = subprotocols

    @classmethod
    def from_json(cls, protocol: Mapping[str, Any]) -> Protocol:
        return cls(protocol["name"], protocol["escaped"], protocol["subprotocols"])

    def get_subprotocols(self) -> List[str]:
        subprotocols = self.subprotocols.split(";")
        if len(subprotocols) > 0 and subprotocols[0] == "":
            return []
        return subprotocols

    def add_subprotocol(self, subprotocol: str, *, initialize_defaults: bool = True) -> None:
        if len(self.subprotocols) == 0:
            self.subprotocols += subprotocol 
        else:
            self.subprotocols += ";" + subprotocol
        
        if not initialize_defaults:
            return

        # Add default general and watercontrol
        full_protocol = f"{self.escaped}/{subprotocol}"
        watercontrol = PWatercontrol(full_protocol, False, 0, 0)
        db.session.add(watercontrol)
        general = PGeneral(full_protocol, 10, "", "Leicht")
        db.session.add(general)

    def remove_subprotocol(self, subprotocol: str) -> None:
        subprotocols = self.get_subprotocols() 
        subprotocols.remove(subprotocol)
        self.subprotocols = ";".join(subprotocols)

class General(db.Model):
    __tablename__ = "general"

    animal_id: Mapped[str] = db.Column(db.String, primary_key=True)
    start: Mapped[str] = db.Column(db.String, primary_key=False)
    end: Mapped[str] = db.Column(db.String, primary_key=False)
    experiment: Mapped[str] = db.Column(db.String, primary_key=False)
    start_weight: Mapped[float] = db.Column(db.Float, primary_key=False)
    watercontrol: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    weights: Mapped[str] = db.Column(db.String, primary_key=False)
    watercontrol_mask: Mapped[str] = db.Column(db.String, primary_key=False)
    suffering: Mapped[str] = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id: str, experiment: str, watercontrol: bool, suffering: str) -> None:
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
    def from_json(cls, general: Mapping[str, Any]) -> General:
        entry = cls(
            general["animal_id"],
            general["experiment"],
            general["watercontrol"],
            general["suffering"],
        )
        entry.start = general["start"]
        entry.end = general["end"]
        entry.start_weight = float(general["start_weight"])
        entry.weights = general["weights"]
        entry.watercontrol_mask = general["watercontrol_mask"]
        return entry

    def set_start_weight(self, start_weight: float) -> None:
        self.start_weight = start_weight
        if start_weight > 0:
            rows = db.session.query(Medication).filter_by(animal_id=self.animal_id)
            if rows.first(): 
                for row in rows: 
                    row.update_amount()

    def get_last_measured_weight(self) -> float | None:
        return next((weight for weight in reversed(json.loads(self.weights))
                     if type(weight) in (int, float) and weight > 0 and math.isfinite(weight)), None)


class Medication(db.Model): 
    __tablename__ = "medication"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    animal_id: Mapped[str] = db.Column(db.String, primary_key=False)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    kind: Mapped[str] = db.Column(db.String, primary_key=False)
    amount: Mapped[str] = db.Column(db.String, primary_key=False)
    concentration: Mapped[str] = db.Column(db.String, primary_key=False)
    dosis: Mapped[str] = db.Column(db.String, primary_key=False)
    weight_independant: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    toe_pinch: Mapped[bool] = db.Column(db.Boolean, primary_key=False)
    procedure: Mapped[str] = db.Column(db.String, primary_key=False)
    protocol_entry_uuid: Mapped[str] = db.Column(db.String, primary_key=False)

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
    ) -> None:
        """! Initializes Medication. 

        Uses `procedure` as a placeholder for date, to ensure uniqueness (since
        medication might be added multiple days. Later the dates will be
        succesive dates. 
        """
        self.uuid = str(uuid.uuid4())
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
        self.update_amount()

    @classmethod
    def from_default(cls, animal_id: str, medication: PMedication) -> Medication:
        return cls(
            animal_id, 
            medication.name, 
            medication.kind, 
            medication.procedure,
            medication.amount,
            medication.concentration, 
            medication.dosis, 
            medication.weight_independant, 
            toe_pinch=medication.kind == "Anesthetic",
            protocol_entry_uuid=medication.uuid
        )

    @classmethod
    def from_form(cls, animal_id: str, medication: Mapping[str, Any]) -> Medication:
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
    def from_json(cls, medication: Mapping[str, Any]) -> Medication:
        return cls.from_form(medication["animal_id"], medication)

    def update(self, medication: Mapping[str, Any]) -> None:
        self.kind = medication["kind"] 
        self.procedure = medication["procedure"]
        self.amount = medication["amount"]
        self.concentration = medication["concentration"] 
        self.dosis = medication["dosis"] 
        self.weight_independant = "weight_independant" in medication
        self.toe_pinch = "toe_pinch" in medication 
        self.update_amount()

    def string(self) -> str:
        return f"{self.name} ({self.concentration} mg/ml)"

    def update_amount(self) -> None:
        def get_start_weight(general: General) -> float:
            print("Start weight: ", general.start_weight)
            return general.start_weight if general.start_weight > 0 else 30

        def get_cur_weight() -> float:
            general = db.session.get(General, self.animal_id) 
            if general is None:
                raise EntryNotFound(f"Experiment data for {self.animal_id} not found")
            print("general start: ", general.start)
            procedure = Procedure.query.filter(
                Procedure.animal_id==self.animal_id,
                Procedure.name==self.procedure
            ).first()
            if procedure is None: 
                return get_start_weight(general)
            print("procedure start: ", procedure.start_date)

            if not date_filled(procedure.start_date) or not date_filled(general.start):
                return get_start_weight(general)
            days_after_start = len(daterange_str(general.start, procedure.start_date))
            weights = json.loads(general.weights)
            print("weights: ", len(weights), days_after_start)
            if days_after_start < len(weights):
                weight = weights[days_after_start]
                if weight is not None and weight > 0:
                    return weight
            return get_start_weight(general)

        if not self.weight_independant: 
            cur_weight = get_cur_weight()
            print("weight @ procedure: ", cur_weight)
            float_dosis = get_float(self.dosis)
            float_concentration = get_float(self.concentration)
            if float_concentration <= 0:
                raise InvalidTypeException("Medication concentration must be greater than zero")
            self.amount = str(roundup((float_dosis*cur_weight)/float_concentration))

class Procedure(db.Model): 
    __tablename__ = "procedures"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    animal_id: Mapped[str] = db.Column(db.String, primary_key=False)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    start_date: Mapped[str] = db.Column(db.String, primary_key=False)
    end_date: Mapped[str] = db.Column(db.String, primary_key=False)
    experimenter: Mapped[str] = db.Column(db.String, primary_key=False)
    protocol_entry_uuid: Mapped[str] = db.Column(db.String, primary_key=False)

    def __init__(
        self, 
        animal_id: str, 
        name: str, 
        start: str, 
        end: str, 
        experimenter: str,
        protocol_entry_uuid: str = ""
    ) -> None:
        self.uuid = str(uuid.uuid4())
        self.animal_id = animal_id 
        self.name = name 
        self.start_date = unify_date(start)
        self.end_date = unify_date(end)
        self.experimenter = experimenter
        self.protocol_entry_uuid = protocol_entry_uuid

    @classmethod 
    def from_default(cls, animal_id: str, experimenter: str, procedure: PProcedure) -> Procedure:
        return cls(
            animal_id, 
            procedure.name, 
            str(procedure.days_after_start) if procedure.days_after_start is not None else "",
            "", 
            experimenter, 
            procedure.uuid
        )

    @classmethod 
    def from_form(cls, animal_id: str, p: Mapping[str, Any]) -> Procedure:
        print("Got dict: ", p)
        return cls(
            animal_id, 
            p["name"], 
            p["start_date"], 
            p["end_date"], 
            p["experimenter"],
            p["protocol_entry_uuid"]
        )

    @classmethod 
    def from_json(cls, procedure: Mapping[str, Any]) -> Procedure:
        return cls.from_form(procedure["animal_id"], procedure)

    def update(self, p: Mapping[str, Any]) -> None:
        self.name = p["name"]
        self.start_date = unify_date(p["start_date"])
        self.end_date = unify_date(p["end_date"])
        self.experimenter = p["experimenter"]

    def set_date(self, date: str) -> None:
        # no need to unify, since date comes from death-date which is already unified.
        self.start_date = date
        self.end_date = date

class Virus(db.Model): 
    __tablename__ = "virus"

    uuid: Mapped[str] = db.Column(db.String, primary_key=True)
    animal_id: Mapped[str] = db.Column(db.String, primary_key=False)
    name: Mapped[str] = db.Column(db.String, primary_key=False)
    procedure: Mapped[str] = db.Column(db.String, primary_key=False)
    amount: Mapped[str] = db.Column(db.String, primary_key=False)
    protocol_entry_uuid: Mapped[str] = db.Column(db.String, primary_key=False)

    def __init__(self, animal_id: str, name: str, procedure: str, amount: str, protocol_entry_uuid: str = "") -> None:
        self.uuid = str(uuid.uuid4())
        self.animal_id = animal_id 
        self.name = name
        self.procedure = procedure 
        self.amount = amount
        self.protocol_entry_uuid = protocol_entry_uuid

    @classmethod 
    def from_default(cls, animal_id: str, virus: PVirus) -> Virus:
        return cls(animal_id, virus.name, virus.procedure, virus.amount, virus.uuid)

    @classmethod 
    def from_form(cls, animal_id: str, virus: Mapping[str, Any]) -> Virus:
        return cls(animal_id, virus["name"], virus["procedure"], virus["amount"])

    @classmethod 
    def from_json(cls, virus: Mapping[str, Any]) -> Virus:
        return cls.from_form(virus["animal_id"], virus)

    def update(self, virus: Mapping[str, Any]) -> None:
        self.procedure = virus["procedure"]
        self.amount = virus["amount"]

    def string(self) -> str:
        return f"{self.name}"

@overload
def table_to_json(table: str) -> str: ...


@overload
def table_to_json(table: Model | SimpleNamespace) -> dict[str, Any]: ...


def table_to_json(table: object) -> dict[str, Any] | str:
    """! Removes fields added by sql-alchamy. """
    if not isinstance(table, str):
        return {k:v for (k,v) in table.__dict__.items() if k[0] != "_"}
    return table


EXPERIMENT_TABLES = {
    "medication": Medication, 
    "procedures": Procedure,
    "viruses": Virus 
}
EXPERIMENT_TABLES_REDUCED = {
    "medication": Medication, 
    "procedures": Procedure,
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
    "lines": ALine, 
    "medication": AMedication, 
    "procedures": AProcedure, 
    "viruses": AVirus
}

def drop(name: str, Table: type[Any], confirm: bool = False) -> None:
    inp = ""
    if confirm:
        inp = input(f"Are you sure you want to drop table {name} (yes/no): ")
    if not confirm or inp == "yes":
        Table.__table__.drop(db.engine)
        print(f"Table {name} droped!")
    else:
        print(f"Table {name} not droped")

def drop_all(tables: Mapping[str, type[Any]], confirm: bool = False) -> None:
    for name, Table in tables.items(): 
        drop(name, Table, confirm)

def roundup(x: float) -> int:
    x = int(math.ceil(x / 10.0)) * 10
    return x

def get_float(text: str) -> float: 
    try:
        # Preserve the existing notation for dose ranges, e.g. 12/14 or 12-14.
        value = str(text)
        for delimiter in ("-", "/"):
            if delimiter in value:
                value = value.split(delimiter)[0]
        number = float(value)
    except (ValueError, TypeError) as error:
        raise InvalidTypeException(f"Invalid medication number: {text}") from error
    if not math.isfinite(number) or number < 0:
        raise InvalidTypeException(f"Invalid medication number: {text}")
    return number

def parse_comment(comment: str) -> Tuple[str, str, float]: 
    """! Gets start and end date from comment"""
    def parse_date(date_str: str) -> str:
        x = re.search(r"(\d{1,4}(/|.|-)\d{1,2}(/|.|-)\d{1,4})", date_str)
        if x is None:
            raise ValueError(f"No date found in {date_str}")
        return unify_date(x.group(1))
    
    def parse_weight(weight_str: str) -> float:
        x = re.search(r"(\d{1,2}(\.\d{1,2})?)g?", weight_str)
        if x is None:
            raise ValueError(f"No weight found in {weight_str}")
        return float(x.group(1))

    def extract(name: str, parts: List[str], expected_length: int, parse: Callable[[str], T]) -> T | None:
        for part in parts: 
            if name in part: 
                try: 
                    index = part.find(":")+1
                    return parse(part[index:index+expected_length])
                except Exception as err: 
                    print("  Could not parse: ", name, part, err)
        return None

    def extract_date(name: str, parts: List[str]) -> str | None:
        return extract(name, parts, 11, parse_date)

    def extract_weight(name: str, parts: List[str]) -> float | None:
        return extract(name, parts, 7, parse_weight)

    # If return empty start and end date if anything should go wrong
    # (invalid comments should not block importing)
    try: 
        parts = comment.split(";")
    except Exception as err: 
        print("Failed parsing dates: ", err)
        return "", "", 0
    start = extract_date("start:", parts) or extract_date("start", parts) or ""
    end = extract_date("end", parts) or ""
    weight = extract_weight("start weight", parts) or 0
    return start, end, weight
