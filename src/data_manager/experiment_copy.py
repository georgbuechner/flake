"""Prepare independent animal data copies before replacing any destination rows."""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, TypedDict
from uuid import uuid4

from werkzeug.exceptions import Forbidden

from data_manager.tables import (
    AnimalData, EXPERIMENT_TABLES, General, Medication, PROTOCOL_TABLES,
    PProcedure, Procedure, User, db,
)
from exceptions.exceptions import EntryNotFound, InvalidTypeException
from utils.dt_utils import SOURCE_DATE_FORMAT

Row = dict[str, Any]


@dataclass
class AnimalCopyPlan:
    animal_id: str
    rows: dict[str, list[Row]]
    start: str
    sacrifice_date: str


class CopyAnimalDates(TypedDict):
    animal_id: str
    start: str
    sacrifice_date: str
    dob: str


class CopyPreview(TypedDict):
    source: CopyAnimalDates
    counts: dict[str, int]
    targets: list[CopyAnimalDates]


class CopySummary(TypedDict):
    source_id: str
    target_ids: list[str]
    categories: list[str]
    copied_rows: int
    skipped_ids: list[str]


def preview_experiment_copy(source_id: str, target_ids: list[str], actor: User) -> CopyPreview:
    """Read current source counts and destination dates without changing data."""
    _validate_animals(source_id, target_ids, require_targets=False)
    return {
        "source": _animal_dates(source_id, actor),
        "counts": {category: Table.query.filter_by(animal_id=source_id).count()
                   for category, Table in EXPERIMENT_TABLES.items()},
        "targets": [_animal_dates(animal_id, actor) for animal_id in dict.fromkeys(target_ids)],
    }


def prepare_experiment_copy(
    source_id: str, target_ids: list[str], categories: list[str],
    date_mode: str, actor: User,
    target_dates: dict[str, dict[str, str]] | None = None, skip_ids: list[str] | None = None,
) -> list[AnimalCopyPlan]:
    """Validate the entire batch, including dates and links, without writing rows."""
    _validate_request(source_id, target_ids, categories, date_mode)
    _validate_date_choices(target_ids, target_dates, skip_ids)
    source = _get_general(source_id, actor)
    source_start = _required_date(source.start, f"Animal {source_id}: experiment start date")
    selected = {category: _read_rows(EXPERIMENT_TABLES[category], source_id)
                for category in dict.fromkeys(categories)}
    for category, rows in selected.items():
        if not rows:
            raise InvalidTypeException(f"Animal {source_id}: no {category} entries to copy.")
    procedures = _source_procedures(source_id, selected)
    return [
        _prepare_target(target_id, actor, selected, procedures, source_start, date_mode,
                        (target_dates or {}).get(target_id, {}))
        for target_id in dict.fromkeys(target_ids) if target_id not in (skip_ids or [])
    ]


def apply_experiment_copy(plan: AnimalCopyPlan) -> None:
    """Replace selected categories and calculate amounts; the caller commits once."""
    general = db.session.get(General, plan.animal_id)
    animal = db.session.get(AnimalData, plan.animal_id)
    if general is None or animal is None:
        raise EntryNotFound(f'Animal "{plan.animal_id}" has no experiment data.')
    dates_changed = general.start != plan.start or animal.death_date != plan.sacrifice_date
    general.start = plan.start
    animal.death_date = plan.sacrifice_date
    if dates_changed and "procedures" not in plan.rows:
        for procedure in Procedure.query.filter_by(animal_id=plan.animal_id):
            template = db.session.get(PProcedure, procedure.protocol_entry_uuid)
            if template is not None and template.days_after_start == "-1":
                procedure.set_date(plan.sacrifice_date)
    for category in plan.rows:
        Table = EXPERIMENT_TABLES[category]
        for row in Table.query.filter_by(animal_id=plan.animal_id):
            db.session.delete(row)
    db.session.flush()
    for category, rows in plan.rows.items():
        db.session.execute(EXPERIMENT_TABLES[category].__table__.insert(), rows)
    if "medication" in plan.rows or "procedures" in plan.rows or dates_changed:
        for medication in Medication.query.filter_by(animal_id=plan.animal_id):
            medication.update_amount()


def _validate_request(source_id: str, target_ids: list[str], categories: list[str], date_mode: str) -> None:
    _validate_animals(source_id, target_ids, require_targets=True)
    if not isinstance(categories, list) or not categories or any(
        not isinstance(value, str) or value not in EXPERIMENT_TABLES for value in categories
    ):
        raise InvalidTypeException("Select procedures, medication and/or viruses.")
    if date_mode not in ("keep", "shift"):
        raise InvalidTypeException("Choose whether to keep or shift the original dates.")


def _validate_animals(source_id: str, target_ids: list[str], *, require_targets: bool) -> None:
    if not isinstance(source_id, str) or not source_id:
        raise InvalidTypeException("Select a source animal.")
    if not isinstance(target_ids, list) or (require_targets and not target_ids) or any(
        not isinstance(value, str) or not value for value in target_ids
    ):
        raise InvalidTypeException("Select at least one destination animal.")
    if source_id in target_ids:
        raise InvalidTypeException("The source animal cannot also be a destination.")


def _validate_date_choices(
    target_ids: list[str], target_dates: dict[str, dict[str, str]] | None, skip_ids: list[str] | None,
) -> None:
    if skip_ids is not None and (not isinstance(skip_ids, list) or any(
        not isinstance(value, str) or value not in target_ids for value in skip_ids
    )):
        raise InvalidTypeException("Only selected destination animals can be skipped.")
    if target_dates is not None and (not isinstance(target_dates, dict) or any(
        animal_id not in target_ids or not isinstance(dates, dict) or any(
            field not in ("start", "sacrifice_date") or not isinstance(value, str)
            for field, value in dates.items()
        ) for animal_id, dates in target_dates.items()
    )):
        raise InvalidTypeException("Provide start and sacrifice dates for selected destinations only.")


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


def _date_text(value: object) -> str:
    try:
        return datetime.strptime(value, SOURCE_DATE_FORMAT).strftime(SOURCE_DATE_FORMAT) if isinstance(value, str) else ""
    except ValueError:
        return ""


def _animal_dates(animal_id: str, actor: User) -> CopyAnimalDates:
    general = _get_general(animal_id, actor)
    animal = db.session.get(AnimalData, animal_id)
    assert animal is not None  # _get_general verifies the animal and its ownership.
    return {"animal_id": animal_id, "start": _date_text(general.start),
            "sacrifice_date": _date_text(animal.death_date), "dob": _date_text(animal.dob)}


def _resolve_dates(general: General, animal: AnimalData, choices: dict[str, str]) -> tuple[str, str]:
    values = {}
    for field, stored, label in (("start", general.start, "experiment start date"),
                                  ("sacrifice_date", animal.death_date, "sacrifice date")):
        existing = _date_text(stored)
        chosen = choices.get(field, existing)
        value = _required_date(chosen, f"Animal {animal.mla_num}: {label}")
        text = value.strftime(SOURCE_DATE_FORMAT)
        if existing and text != existing:
            raise InvalidTypeException(f"Animal {animal.mla_num}: {label} already exists. Reload the preview.")
        if _date_text(animal.dob) and value < _required_date(animal.dob, "Date of birth"):
            raise InvalidTypeException(f"Animal {animal.mla_num}: {label} is before its date of birth.")
        values[field] = text
    if values["sacrifice_date"] < values["start"]:
        raise InvalidTypeException(f"Animal {animal.mla_num}: sacrifice date is before its experiment start date.")
    return values["start"], values["sacrifice_date"]


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
    source_start: datetime, date_mode: str, choices: dict[str, str],
) -> AnimalCopyPlan:
    general = _get_general(target_id, actor)
    animal = db.session.get(AnimalData, target_id)
    assert animal is not None
    start, death_date = _resolve_dates(general, animal, choices)
    target_start = _required_date(start, f"Animal {target_id}: experiment start date")
    shift = target_start - source_start if date_mode == "shift" else timedelta()
    rows = {
        category: [_clone_row(category, row, target_id, general.experiment) for row in values]
        for category, values in selected.items()
    }
    dated = [_shift_procedure(row, shift, death_date) for row in rows.get("procedures", procedures)]
    final_procedures = dated if "procedures" in selected else _read_rows(Procedure, target_id)
    if "procedures" not in selected and animal.death_date != death_date:
        final_procedures = [_fill_sacrifice(row, death_date) for row in final_procedures]
    if "procedures" not in selected:
        _check_existing_dates(target_id, dated, final_procedures)
    if "procedures" in rows:
        for row, dates in zip(rows["procedures"], dated):
            row.update(start_date=dates["start_date"], end_date=dates["end_date"])
    _check_final_links(target_id, rows, final_procedures)
    return AnimalCopyPlan(target_id, rows, start, death_date)


def _is_sacrifice(row: Row) -> bool:
    template = db.session.get(PProcedure, row["protocol_entry_uuid"]) if row["protocol_entry_uuid"] else None
    return template is not None and template.days_after_start == "-1"


def _fill_sacrifice(row: Row, death_date: str) -> Row:
    return {**row, "start_date": death_date, "end_date": death_date} if _is_sacrifice(row) else row


def _shift_procedure(row: Row, shift: timedelta, death_date: str) -> Row:
    if _is_sacrifice(row):
        return {**row, "start_date": death_date, "end_date": death_date}
    try:
        return {
            **row,
            "start_date": (datetime.strptime(row["start_date"], SOURCE_DATE_FORMAT) + shift).strftime(SOURCE_DATE_FORMAT),
            "end_date": (datetime.strptime(row["end_date"], SOURCE_DATE_FORMAT) + shift).strftime(SOURCE_DATE_FORMAT),
        }
    except OverflowError as error:
        raise InvalidTypeException(f'Procedure "{row["name"]}" falls outside the supported date range.') from error


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
    if original is not None and all(getattr(original, key) == value for key, value in criteria.items()):
        default = original
    else:
        matches = Table.query.filter_by(**criteria).all()
        if len(matches) > 1 and category != "procedures":
            # Identify the template independently of the animal's editable association.
            procedure = original.procedure if original is not None else row["procedure"]
            matches = [entry for entry in matches if entry.procedure == procedure]
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
