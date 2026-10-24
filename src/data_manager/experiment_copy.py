"""Prepare independent animal data copies before replacing any destination rows."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, TypedDict
from uuid import uuid4

from werkzeug.exceptions import Forbidden

from data_manager.tables import (
    AnimalData, EXPERIMENT_TABLES, General, Medication, PROTOCOL_TABLES,
    Procedure, User, db,
)
from exceptions.exceptions import EntryNotFound, InvalidTypeException
from utils.dt_utils import SOURCE_DATE_FORMAT

Row = dict[str, Any]


@dataclass
class AnimalCopyPlan:
    animal_id: str
    rows: dict[str, list[Row]]


class CopySummary(TypedDict):
    source_id: str
    target_ids: list[str]
    categories: list[str]
    copied_rows: int


def prepare_experiment_copy(
    source_id: str, target_ids: list[str], categories: list[str],
    date_mode: str, actor: User,
) -> list[AnimalCopyPlan]:
    """Validate the entire batch, including dates and links, without writing rows."""
    _validate_request(source_id, target_ids, categories, date_mode)
    source = _get_general(source_id, actor)
    source_start = _required_date(source.start, f"Animal {source_id}: experiment start date")
    selected = {category: _read_rows(EXPERIMENT_TABLES[category], source_id)
                for category in dict.fromkeys(categories)}
    for category, rows in selected.items():
        if not rows:
            raise InvalidTypeException(f"Animal {source_id}: no {category} entries to copy.")
    procedures = _source_procedures(source_id, selected)
    return [
        _prepare_target(target_id, actor, selected, procedures, source_start, date_mode)
        for target_id in dict.fromkeys(target_ids)
    ]


def apply_experiment_copy(plan: AnimalCopyPlan) -> None:
    """Replace selected categories and calculate amounts; the caller commits once."""
    for category in plan.rows:
        Table = EXPERIMENT_TABLES[category]
        for row in Table.query.filter_by(animal_id=plan.animal_id):
            db.session.delete(row)
    db.session.flush()
    for category, rows in plan.rows.items():
        db.session.execute(EXPERIMENT_TABLES[category].__table__.insert(), rows)
    if "medication" in plan.rows:
        for medication in Medication.query.filter_by(animal_id=plan.animal_id):
            medication.update_amount()


def _validate_request(source_id: str, target_ids: list[str], categories: list[str], date_mode: str) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise InvalidTypeException("Select a source animal.")
    if not isinstance(target_ids, list) or not target_ids or any(
        not isinstance(value, str) or not value for value in target_ids
    ):
        raise InvalidTypeException("Select at least one destination animal.")
    if source_id in target_ids:
        raise InvalidTypeException("The source animal cannot also be a destination.")
    if not isinstance(categories, list) or not categories or any(
        not isinstance(value, str) or value not in EXPERIMENT_TABLES for value in categories
    ):
        raise InvalidTypeException("Select procedures, medication and/or viruses.")
    if date_mode not in ("keep", "shift"):
        raise InvalidTypeException("Choose whether to keep or shift the original dates.")


def _get_general(animal_id: str, actor: User) -> General:
    animal = db.session.get(AnimalData, animal_id)
    if animal is None:
        raise EntryNotFound(f'Animal "{animal_id}" not found.')
    if not actor.admin and animal.user != actor.name:
        raise Forbidden(f'You cannot copy experiment data for animal "{animal_id}".')
    general = db.session.get(General, animal_id)
    if general is None:
        raise EntryNotFound(f'Animal "{animal_id}" has no experiment data. Select a subprotocol first.')
    return general


def _read_rows(Table: type[Any], animal_id: str) -> list[Row]:
    return [
        {column.name: getattr(row, column.name) for column in Table.__table__.columns}
        for row in Table.query.filter_by(animal_id=animal_id)
    ]


def _required_date(value: object, description: str) -> datetime:
    try:
        if not isinstance(value, str):
            raise ValueError
        return datetime.strptime(value, SOURCE_DATE_FORMAT)
    except ValueError as error:
        raise InvalidTypeException(f"{description} is missing or invalid. Nothing was copied.") from error


def _procedure_dates(row: Row, animal_id: str) -> tuple[datetime, datetime]:
    description = f'Animal {animal_id}, procedure "{row["name"]}"'
    start = _required_date(row["start_date"], f"{description}: start date")
    end = _required_date(row["end_date"], f"{description}: end date")
    if end < start:
        raise InvalidTypeException(f"{description}: end date is before its start date.")
    return start, end


def _source_procedures(source_id: str, selected: dict[str, list[Row]]) -> list[Row]:
    names = {row["procedure"] for category, rows in selected.items()
             if category != "procedures" for row in rows}
    procedures = selected["procedures"] if "procedures" in selected else _read_rows(Procedure, source_id)
    if names - {row["name"] for row in procedures}:
        raise InvalidTypeException(f"Animal {source_id}: a copied entry has no associated procedure.")
    if "procedures" not in selected:
        procedures = [row for row in procedures if row["name"] in names]
    for row in procedures:
        _procedure_dates(row, source_id)
    return procedures


def _prepare_target(
    target_id: str, actor: User, selected: dict[str, list[Row]], procedures: list[Row],
    source_start: datetime, date_mode: str,
) -> AnimalCopyPlan:
    general = _get_general(target_id, actor)
    target_start = _required_date(general.start, f"Animal {target_id}: experiment start date")
    shift = target_start - source_start if date_mode == "shift" else timedelta()
    dated = [_shift_procedure(row, shift) for row in procedures]
    final_procedures = dated if "procedures" in selected else _read_rows(Procedure, target_id)
    if "procedures" not in selected:
        _check_existing_dates(target_id, dated, final_procedures)
    rows = {
        category: [_clone_row(category, row, target_id, general.experiment) for row in values]
        for category, values in selected.items()
    }
    if "procedures" in rows:
        for row, dates in zip(rows["procedures"], dated):
            row.update(start_date=dates["start_date"], end_date=dates["end_date"])
    _check_final_links(target_id, rows, final_procedures)
    return AnimalCopyPlan(target_id, rows)


def _shift_procedure(row: Row, shift: timedelta) -> Row:
    return {
        **row,
        "start_date": (datetime.strptime(row["start_date"], SOURCE_DATE_FORMAT) + shift).strftime(SOURCE_DATE_FORMAT),
        "end_date": (datetime.strptime(row["end_date"], SOURCE_DATE_FORMAT) + shift).strftime(SOURCE_DATE_FORMAT),
    }


def _check_existing_dates(target_id: str, expected: list[Row], existing: list[Row]) -> None:
    for name in {row["name"] for row in expected}:
        matches = [row for row in existing if row["name"] == name]
        for row in matches:
            _procedure_dates(row, target_id)
        dates = lambda rows: Counter((row["start_date"], row["end_date"]) for row in rows if row["name"] == name)
        if dates(matches) != dates(expected):
            raise InvalidTypeException(
                f'Animal {target_id}: dates for procedure "{name}" do not match. '
                "Include procedures in the copy to apply the selected dates."
            )


def _clone_row(category: str, row: Row, target_id: str, protocol: str) -> Row:
    Table = PROTOCOL_TABLES[category]
    original = db.session.get(Table, row["protocol_entry_uuid"]) if row["protocol_entry_uuid"] else None
    criteria = {"protocol": protocol, "name": row["name"]}
    if category != "procedures":
        criteria["procedure"] = row["procedure"]
    if original is not None and all(getattr(original, key) == value for key, value in criteria.items()):
        default = original
    else:
        matches = Table.query.filter_by(**criteria).all()
        if len(matches) != 1:
            raise InvalidTypeException(
                f'Animal {target_id}: no unique {category} protocol entry for "{row["name"]}".'
            )
        default = matches[0]
    return {**row, "uuid": str(uuid4()), "animal_id": target_id, "protocol_entry_uuid": default.uuid}


def _check_final_links(target_id: str, selected: dict[str, list[Row]], procedures: list[Row]) -> None:
    names = {row["name"] for row in procedures}
    for category in ("medication", "viruses"):
        rows = selected.get(category)
        if rows is None:
            rows = _read_rows(EXPERIMENT_TABLES[category], target_id)
        for row in rows:
            if row["procedure"] not in names:
                raise InvalidTypeException(
                    f'Animal {target_id}: {category} "{row["name"]}" requires missing '
                    f'procedure "{row["procedure"]}".'
                )
