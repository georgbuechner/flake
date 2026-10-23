from urllib.parse import unquote
import clevercsv 
import json
import math
import os
import random
import string
import pandas as pd
from copy import deepcopy
from collections import OrderedDict
from types import SimpleNamespace
from flask_sqlalchemy.query import Query
from typing import Dict, List, Tuple, Any
from exceptions.exceptions import (
    AnimalDataIncompleteException,
    ConfirmationRequired,
    DublicateEntry,
    EntryNotFound,
    InvalidNameException,
    InvalidTypeException, 
    MissingEntryException,
    ParseException, 
    WeightGenerationUnavailable,
    InvalidDateException,
)
from utils.parser_weights_and_water import (
    get_water_control_mask, 
    get_estimated_weight_list,
    apply_noise
)
from data_manager.tables import (
    ALine,
    AnimalData,
    CommentBackup,
    CommentData,
    DEFINITION_TABLES,
    EXPERIMENT_TABLES,
    EXPERIMENT_TABLES_REDUCED,
    General,
    Medication,
    Note,
    PGeneral,
    PMedication,
    PProcedure,
    PROTOCOL_TABLES,
    PVirus,
    PWatercontrol,
    Procedure,
    Protocol,
    User,
    VerificationCode,
    Virus,
    db,
    table_to_json,
)
from utils.utils import sort, sort_query, escape, get_signature_path
from utils.dt_utils import * 
from flask import render_template

SACRIFICE_DATE = -1
UNEXPECTED_DEATH = "Death: unexpected"

class DManager:
    """! The data-manager class.

    Provides access to sql-database and handles getting and storing data to
    filesystem (pyrat(=animal) -data) and sql-database (experiment-data).

    @attribute protocols {"name": {"espaped":<str>, "subs":<Dict[str, str]>}
    """

    def __init__(self):
        """! The DManager class initializer. 
        """
        print(f"Initializing DManager...")
        self.mapping = {}
        self.keys_per_language = {}
        with open("resources/mapping.json") as f:
            mapping = json.load(f)
            for language, fields in mapping.items():
                self.mapping.update(fields)
                self.keys_per_language[language] = fields.keys()

    def pyrat_usernames(self) -> List[str]:
        animal_data = AnimalData.query.all()
        users = [*set([str(data.user) for data in animal_data])] 
        users.sort()
        return users

    def pyrat_usernames_with_progress(self, year) -> Dict[str, Tuple[int, int]]:
        """! Gets dictionary of all users (pyrat: 'Responsible') which are
        currently responsible for an animal, mapping to a tuple indicating how
        many animals from all animals of this user are completed (f.e. FLAKE
        5/10)

        @return Dict of users mapping to tuple.
        """
        start_year, end_year = get_reporting_year(int(year))
        animal_data = AnimalData.query.all()
        users = {}
        for data in animal_data: 
            if data.user not in users: 
                users[data.user] = (0, 0)
            progress = users[data.user]
            # Update only if data matches with the current reporting year.
            if in_reporting_year(start_year, end_year, data.death_date):
                progress = (progress[0]+data.stored, progress[1]+1)
            users[data.user] = progress
        users = OrderedDict(sorted(users.items()))
        return users

    def completed_for_year(self, year: str) -> Tuple[int, int]: 
        """! Returns tuple indicating how many animals in the current year have
        been completed" 

        @returns Tuple of two ints (completed/ total)
        """
        start_year, end_year = get_reporting_year(int(year))
        animal_data = AnimalData.query.all()
        total = 0 
        completed = 0
        for data in animal_data: 
            if not in_reporting_year(start_year, end_year, data.death_date):
                continue 
            total += 1 
            completed += data.stored
        return completed, total

    def protocols(self) -> Dict[str, str]:
        """! Gets list of all protocols which are currently
        applied for all animals (refers to pyrat data).

        @return Dict of protocols.
        """
        animal_data = AnimalData.query.all()
        protocols = {
            data.protocol:data.protocol_escaped for data in animal_data if data.protocol_escaped != "---"
        }
        ordered_protocols = OrderedDict(sorted(protocols.items()))
        return ordered_protocols

    def get_notes(self, animal_id: str) -> Dict[str, Tuple[str, bool]]: 
        notes = Note.query.filter(Note.animal_id == animal_id)
        notes_dict = {
            "general":("", False), 
            "viruses":("", False), 
            "medication":("", False), 
            "procedures":("", False)
        }
        for note in notes:
            notes_dict[note.category] = (note.note, note.surgery_sheet)
        return notes_dict

    def protocols_and_subprotocols(self) -> Dict[str, List[str]]: 
        """! Gets all protocols with list of their subprotocols. """
        protocols = {}
        for protocol in Protocol.query.all():
            protocols[protocol.name] = protocol.get_subprotocols()
        return protocols

    def protocol_is_setup(self, escaped_protocol: str) -> bool: 
        protocol = db.session.get(Protocol, escaped_protocol)
        if protocol is None: 
            return False
        for subprotocol in protocol.get_subprotocols(): 
            if not self.subprotocol_is_setup(f"{escaped_protocol}/{subprotocol}"):
                return False
        return True 

    def subprotocol_is_setup(self, full_protocol: str) -> bool: 
        return (
            self.has_sacrifice_procedure(full_protocol) 
            and self.missing_required_medication(full_protocol) is None
            and self.missing_required_virus(full_protocol) is None
        )

    def has_sacrifice_procedure(self, full_protocol: str) -> bool: 
        query = PProcedure.query.filter(
            PProcedure.protocol == full_protocol, PProcedure.name.like("Sacrifice%")
        )
        return True if query.first() else False

    def missing_required_medication(self, full_protocol: str) -> str|None: 
        query = PProcedure.query.filter(PProcedure.protocol == full_protocol)
        if not query.first(): 
            return None
        missing = []
        for procedure in query: 
            if (procedure.requires_medication or 0) > 0:
                query = PMedication.query.filter(
                    PMedication.protocol == full_protocol, PMedication.procedure == procedure.name
                )
                if not query.first(): 
                    missing.append(f"for {procedure.name} missing {procedure.requires_medication}")
                elif procedure.requires_medication-query.count() > 0:
                    missing.append(f"for {procedure.name} missing {procedure.requires_medication-query.count()}")
        return ", ".join(missing) if missing else None

    def missing_required_virus(self, full_protocol: str) -> str|None: 
        query = PProcedure.query.filter(PProcedure.protocol == full_protocol)
        if not query.first(): 
            return None
        missing = []
        for procedure in query: 
            if (procedure.requires_virus or 0) > 0:
                query = PVirus.query.filter(
                    PVirus.protocol == full_protocol, PVirus.procedure == procedure.name
                )
                if not query.first(): 
                    missing.append(f"for {procedure.name} missing {procedure.requires_virus}")
                elif procedure.requires_virus-query.count() > 0:
                    missing.append(f"for {procedure.name} missing {procedure.requires_virus-query.count()}")
        return ", ".join(missing) if missing else None

    def get_overview_table(
        self, 
        initial_query: Query, 
        sort_by: str, 
        reverse: bool, 
        filter_date: str, 
        start: str, 
        end: str, 
        mla_num: str
    ) -> List: 
        # Apply filter 
        if mla_num != "":  
            filtered_query = initial_query.filter(AnimalData.mla_num.like(f"%{mla_num}%"))
        else: 
            filtered_query = initial_query.all()
        if filter_date == "DOB":
            filtered_query = [row for row in filtered_query if row.dob >= f"{start}" and row.dob <= f"{end}"]
        elif filter_date == "Sacrifice date":
            filtered_query = [
                row for row in filtered_query if row.death_date>= f"{start}" and row.death_date <= f"{end}"
            ]
        elif filter_date == "start date": 
            dates = self.get_start_dates(filtered_query) 
            filtered_query = [
                row for row in filtered_query if dates[row.mla_num] >= f"{start}" and dates[row.mla_num] <= f"{end}"
            ]
        # Sort
        sorted_query = sort_query(filtered_query, sort_by)
        # Reverse 
        if reverse != "True":
            sorted_query.reverse()
        return sorted_query 

    def get_current_year(self) -> str: 
        """! Gets current reporting year (the current year, or the last, if it's
        before the 31. of March) """
        print(f"{datetime.now().month}-{datetime.now().day} <= 3-31")
        if f"{datetime.now().month}-{datetime.now().day}" <= "3-31": 
            print("-> ", datetime.now().year-1)
            return str(datetime.now().year-1)
        else: 
            print("-> ", datetime.now())
        return str(datetime.now().year)

    def get_comment_infos(self, animal_data: List[AnimalData]) -> Dict[str, bool]: 
        comment_infos = {} 
        for animal in animal_data: 
            comment_backup = db.session.get(CommentBackup, animal.mla_num)
            comment_infos[animal.mla_num] = comment_backup and comment_backup.comment != ""
        return comment_infos

    def extract_animal_data(self, file, ignore_comment: bool) -> Dict[str, str]:
        """! Extracts and stores animal-data from csv file.

        @param tmp_path  Path for temporarily storing csv-file.
        @return number of animals inserted and html view of inserted animal data
        """
        from pathlib import Path 
        from tempfile import TemporaryDirectory

        if file is None: 
            raise MissingEntryException("csv")
        # Genrate temporary path
        with TemporaryDirectory(prefix="flake-upload-") as directory:
            path = Path(directory) / "animals.csv"
            # temporarily store file
            file.save(str(path))
            # Load file and delete tmp-file afterwards
            all_mlas, updated, = self.__load_animal_data_from_csv(str(path))

        response = {"text":"", "animal_data": ""}
        # If success, update protocols (since new protocols might have been added)
        response["text"] = f"{len(all_mlas)-len(updated)} inserted."
        if len(updated) > 0:
            response["text"] += f" {len(updated)} updated ({' '.join(x for x in updated)})"
        if len(all_mlas) > 0: 
            comment_data = self.__get_parsed_comments_data(all_mlas)
            response["animal_data"] = self.get_quick_apply_animal_data(
                comment_data, ignore_comment=ignore_comment
            )
        return response

    def get_comment_data_html(self, animal_ids: List[str]) -> str: 
        """! Creates a reduceded_overview-html-table for given animals."""
        comment_data = self.__get_parsed_comments_data(animal_ids)
        return self.get_quick_apply_animal_data(comment_data)

    def get_start_dates(self, animals) -> Dict[str, str]: 
        start_dates = {}
        for x in animals: 
            general = db.session.get(General, x.mla_num)
            start_dates[x.mla_num] = general.start if general else "---"
        return start_dates

    def __get_parsed_comments_data(
        self, animal_ids: List[str]
    ) -> Dict[str, CommentData]:
        parsed_comments = {}
        for mla_num in animal_ids: 
            comment = db.session.get(CommentBackup, mla_num)
            if comment:
                parsed_comments[mla_num] = CommentData(comment.comment) 
        return parsed_comments

    def get_quick_apply_animal_data(
        self, 
        comment_data: Dict[str, CommentData], 
        set_stored: bool|None = None, 
        ignore_comment: bool|None = None
    ):
        # Get animal data
        animal_data = []
        for mla, _ in comment_data.items(): 
            animal = db.session.get(AnimalData, mla)
            if animal:
                if set_stored != None:
                    animal.stored = set_stored
                if ignore_comment: 
                    comment_data[mla] = CommentData("") # Use empty comment
                animal_data.append(animal) 
        return render_template(
            "overview_table_reduced.html", 
            animal_data=animal_data,
            comment_data=comment_data,
            protocols=self.protocols_and_subprotocols(),
        )

    def set_protocol(
        self, animal_id: str, protocol: str, force: bool, commit: bool = True
    ) -> str:
        x, _ = self.__is_stored(animal_id, ignore_death_date=True)
        if x > 0 and force is False: 
            raise ConfirmationRequired(
                f"{round((x/33)*100, 2)}% of data already filled. " \
                "Are you sure, you want to proceed?" 
            )
        escaped_protocol = escape(protocol)
        animal_data = db.session.get(AnimalData, animal_id)
        if animal_data is None: 
            raise EntryNotFound(f"AnimalData for {animal_id} not found")
        animal_data.protocol = protocol
        animal_data.protocol_escaped = escaped_protocol
        animal_data.subprotocol = "---"
        self.__clear_experiment_data(animal_id)
        return escaped_protocol

    def set_subprotocol(
        self, animal_id: str, subprotocol: str, force: bool
    ) -> None:
        """! Updates subprotocol entry and initializes experiment-data.

        Uses the matching protocol and subprotocol to initialize the
        experiment-data with default values.

        @param animal_id  ID of animal.
        @param subprotocol  Subprotocol which to use for this animal.
        """
        x, _ = self.__is_stored(animal_id, ignore_death_date=True)
        if x > 0 and force is False: 
            raise ConfirmationRequired(
                f"{round((x/33)*100, 2)}% of data already filled. " \
                "Sure you want proceed?"
            )
        print("set_subprotocol for: ", animal_id)
        animal_data = db.session.get(AnimalData, animal_id)
        if animal_data is None: 
            raise EntryNotFound(f"AnimalData for {animal_id} not found")
        animal_data.subprotocol = subprotocol
        if subprotocol == "---":
            self.__clear_experiment_data(animal_id)
            return 
        full_protocol = f"{animal_data.protocol_escaped}/{subprotocol}"
        # Clear all existing data
        self.__clear_experiment_data(animal_id)
        # Initialize general 
        watercontrol = db.session.query(PWatercontrol).filter_by(
            protocol=full_protocol
        ).first()
        if watercontrol is None: 
            raise EntryNotFound(
                f"No watercontrol found for '{animal_data}' in {full_protocol}'."
            )
        default_general = db.session.query(PGeneral).filter_by(
            protocol=full_protocol
        ).first()
        if default_general is None: 
            raise EntryNotFound(
                f"No default protocol found for '{animal_data}' in {full_protocol}'."
            )
        general = General(
            animal_id, 
            full_protocol, 
            watercontrol.allowed, 
            default_general.suffering
        )
        db.session.add(general)
        # Initialize procedures:
        for protocol_procedure in db.session.query(PProcedure).filter_by(protocol=full_protocol): 
            if not protocol_procedure.optional:
                procedure = Procedure.from_default(animal_id, animal_data.user, protocol_procedure)
                db.session.add(procedure)
        # Initialize medication:
        for protocol_medication in db.session.query(PMedication).filter_by(protocol=full_protocol):
            entry = Medication.from_default(animal_id, protocol_medication)
            db.session.add(entry)
        # Initialize virus:
        for protocol_virus in db.session.query(PVirus).filter_by(protocol=full_protocol):
            if not protocol_virus.optional:
                entry = Virus.from_default(animal_id, protocol_virus)
                db.session.add(entry)
        # If sacrifice-date already exists, set sacrifice-date for procedures referencing sacrifice-date
        fill_sacrifice_date(animal_id)

    def set_death_date(
        self, animal_id: str, death_date: str, *, regenerate_weights: bool = True
    ) -> str | None:
        if death_date not in (None, "", "---"):
            strtodate(death_date)
        animal_data = db.session.get(AnimalData, animal_id)
        if animal_data is None: 
            raise EntryNotFound(f"AnimalData for {animal_id} not found")

        animal_data.death_date = death_date
        warning = None
        # Update medication/ procedures referencing sacrifice date (-1)
        if animal_data.protocol_escaped != "---" and animal_data.subprotocol != "---":
            full_protocol = f"{animal_data.protocol_escaped}/{animal_data.subprotocol}"
            fill_sacrifice_date(animal_id)
            # If experiment-data already exists, re-generate weights.
            general = db.session.get(General, animal_id)
            if general and regenerate_weights:
                start_weight = general.start_weight if general.start_weight > 0 else -1
                print(f"generating weights: {animal_id}, {start_weight}")
                warning = self.try_generate_weight_list(animal_id, start_weight)
            self.__update_stored(animal_id)
        return warning

    def update_experiment_data_entry(
        self, animal_id: str, category: str, data: Dict[str, Any]
    ):
        Table = get_category_table(EXPERIMENT_TABLES, category)
        require_entry_fields(category, data, experiment=True)
        # Check name:
        if "name" not in data or data["name"] == "---": 
            raise MissingEntryException(entry="name")
        if category == "procedures" and "experimenter" not in data:
            raise MissingEntryException(entry="experimenter")
        # Update or add element:
        uuid = data.get("uuid", "")
        element = db.session.get(Table, uuid) if uuid else None
        if uuid and (element is None or element.animal_id != animal_id):
            raise EntryNotFound("No entry found for this animal.")
        if element:
            validate_unchanged_name(element, data["name"])
            element.update(data)
        else: 
            if check_experiment_data_entry_exists(Table, category, data, animal_id): 
                raise DublicateEntry(f"A entry for {data['name']} already exists!")
            element = Table.from_form(animal_id, data)
            db.session.add(element)
        # Update stored? of animal-data
        self.__update_stored(animal_id)

    def delete_animal_data(self, animal_id: str) -> None: 
        tables_to_delete = list(EXPERIMENT_TABLES.values())
        tables_to_delete.append(General)
        animal_data = db.session.get(AnimalData, animal_id)
        if animal_data is None:
            raise EntryNotFound(f"Animal not found + {animal_id}")
        for Table in tables_to_delete: 
            rows = Table.query.filter(Table.animal_id == animal_id)
            if rows.first():
                for row in rows:
                    db.session.delete(row)
        db.session.delete(animal_data)

    def reset_animal_data(self, experiment):
        query = General.query.filter(General.experiment == experiment)
        num_data_reset = 0
        if query.first():
            for general in query: 
                num_data_reset += 1
                self.set_subprotocol(general.animal_id, "---", True)
        return num_data_reset 

    def reload_animal_data(self, experiment): 
        query = General.query.filter(General.experiment == experiment)
        saved_data = {}
        response = {"text": "reaload animals"}
        if query.first():
            # Build response
            for general in query: 
                # First generate saved-data from comment
                comment = db.session.get(CommentBackup, general.animal_id)
                comment_str = comment.comment if comment else ""
                comment_data = CommentData(comment_str) 
                # if either start or end are already defined, use them
                if general.start != "": 
                    comment_data.start_date = general.start 
                if general.end != "": 
                    comment_data.end_date = general.end
                saved_data[general.animal_id] = comment_data
            response["animal_data"] = self.get_quick_apply_animal_data(
                saved_data, set_stored=False
            )
            # Set stored to false 
            # reset data: 
            _ = self.reset_animal_data(experiment)
        return response

    def delete_experiment_data_entry(
        self, animal_id: str, category: str, uuid: str
    ) -> None:
        Table = get_category_table(EXPERIMENT_TABLES, category)
        element = db.session.get(Table, uuid)
        if element:
            db.session.delete(element)
        # Update stored? of animal-data
        self.__update_stored(animal_id)
    
    def get_experiment_data(self, animal_id: str) -> Dict[str, Dict[str, Any]]:
        general = db.session.get(General, animal_id)
        experiment_data = {"general": table_to_json(general)}

        for name, Table in EXPERIMENT_TABLES.items(): 
            data = Table.query.filter(Table.animal_id == animal_id)
            # TODO (fux): Check types (it seems like general and other tables
            # have different types?
            experiment_data[name] = [table_to_json(t) for t in data]
        return experiment_data

    def get_surgery_sheet_data(
        self, animal_id: str
    ) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        general = db.session.get(General, animal_id)
        animal_data = db.session.get(AnimalData, general.animal_id)
        data = {"general": table_to_json(general)}
        table_notes = Note.query.filter(Note.animal_id == animal_id, Note.surgery_sheet)
        data["general"]["notes"] = "\n".join([unquote(note.note) for note in table_notes])
        print("NOTES: ", data["general"]["notes"])
        filtered_procedures = []
        # Add information form tables (procedures, viruses etc.)
        for name, Table in EXPERIMENT_TABLES_REDUCED.items(): 
            rows = Table.query.filter(Table.animal_id == animal_id)
            # For procedures, also filter all procedures after animals sacrifice
            if name == "procedures":
                rows, filtered_procedures = remove_procedures_after_death(
                    rows, animal_data.death_date
                )
            # Convert table data to json
            data[name] = rows
        # Add death drugs
        data["death_drugs"] = [
            x for x in data["medication"] if "sacrifice" in x.procedure.lower()
        ]
        # Add unexpected_event and clear death drugs, in case of unexpected death.
        if procedures_contains(data["procedures"], UNEXPECTED_DEATH):
            data["death_drugs"] = []
            data["general"]["unexpected_events"] = f"Unexpected death on {animal_data.death_date}."

        def get_entries_with_dates(table_name: str) -> List[Dict[str, Any]]:
            entries_with_date = []
            for x in data[table_name]: 
                json_data = table_to_json(x)
                # Add entry for each found procedure
                for p in [p for p in data["procedures"] if p.name == x.procedure]:
                    for date in daterange_str(p.start_date, p.end_date):
                        json_data["date"] = date
                        entries_with_date.append(deepcopy(json_data))
            return entries_with_date
        data["medication"] = sort(get_entries_with_dates("medication"), "date")
        data["death_drugs"] = get_entries_with_dates("death_drugs")
        data["viruses"] = sort(get_entries_with_dates("viruses"), "date")
        data["procedures"] = sort([table_to_json(p) for p in data["procedures"]], "start_date")
        return data, filtered_procedures

    def get_protocol_data(self, category: str, full_protocol: str): 
        if category not in ("general", "watercontrol"):
            get_category_table(PROTOCOL_TABLES, category)
        # Get tables which should have only 1 element:
        if category not in PROTOCOL_TABLES:
            if category == "general":
                res = PGeneral.query.filter(PGeneral.protocol == full_protocol)
            if category == "watercontrol":
                res = PWatercontrol.query.filter(PWatercontrol.protocol == full_protocol)
            return table_to_json(res.first()) if res.first() else {}, {}
        # Get tables for all other categories.
        Table = get_category_table(PROTOCOL_TABLES, category)
        protocol_data = Table.query.filter(Table.protocol == full_protocol)
        # Sort tables by days_after_start:
        if category == "procedures":
            protocol_data = sort_query(protocol_data, "days_after_start", to_int=True)
        else: 
            protocol_data = sort_query(protocol_data, "name")
        # Get definitions:
        if category == "allowed_animals":
            escaped_protocol, subprotocol = full_protocol.split("/", 1)
            counts = dict(db.session.query(AnimalData.line, db.func.count()).filter(
                AnimalData.protocol_escaped == escaped_protocol,
                AnimalData.subprotocol == subprotocol,
            ).group_by(AnimalData.line).all())
            configured_names = {line.name for line in protocol_data}
            for line in protocol_data:
                line.used = counts.get(line.name, 0)
            # Display missing allowances without creating database records on GET.
            for name in counts.keys() - configured_names:
                protocol_data.append(SimpleNamespace(
                    uuid="", name=name, used=counts[name], num_availible_animals=None,
                ))
            protocol_data.sort(key=lambda line: line.name)
            available_names = {line.name for line in ALine.query.all()} | counts.keys()
            definitions = [ALine(name) for name in sorted(available_names - configured_names)]
        else:
            definitions = sort_query(get_category_table(DEFINITION_TABLES, category).query.all(), "name")
        return protocol_data, definitions

    def get_p9_data(self, escaped_protocol: str, use_year: str, force: bool): 
        protocol = db.session.get(Protocol, escaped_protocol)
        if protocol is None:
            raise EntryNotFound(f'Protocol "{escaped_protocol}" not found')
        subprotocols = {}
        error_json = {}
        num_errors = 0
        def to_string(elems, procedure): 
            return ", ".join([e.string() for e in elems if e.date in dates])

        def procedures(procedures, medication, viruses, animal_data, num_errors):
            procedures = sort_query(procedures, "start_date")
            # Handle "unexpected death": Remove procedures after animals death
            procedures, filtered_procedures = remove_procedures_after_death(
                procedures, animal_data.death_date
            )
            error_json[animal_data.mla_num] = filtered_procedures
            if len(filtered_procedures) > 0: 
                num_errors += 1
            data = {}

            for p in procedures: 
                # Skip if date not yet filled.
                if not date_filled(p.start_date) or not date_filled(p.end_date):
                    if force: 
                        continue
                    else:
                        raise AnimalDataIncompleteException()
                default = get_protocol_entry_by_name(PProcedure, general.experiment, p.name)
                if default is None and p.name != UNEXPECTED_DEATH: 
                    raise MissingEntryException(
                        entry=p.name, msg=f"For animal: {general.animal_id}: no procedure: "
                    )
                if (p.start_date, p.end_date) not in data: 
                    data[(p.start_date, p.end_date)] = {
                        "start": convert(p.start_date), 
                        "end": convert(p.end_date), 
                        "names": p.name, 
                        "medication": "", 
                        "viruses": "", 
                    }
                else: 
                    data[(p.start_date, p.end_date)]["names"] += f", {p.name}"

                meds = ", ".join([m.string() for m in medication if m.procedure == p.name])
                virs = ", ".join([v.string() for v in viruses if v.procedure == p.name])
                data[(p.start_date, p.end_date)]["medication"] += meds 
                data[(p.start_date, p.end_date)]["viruses"] += virs
            return list(data.values())

        for sub in protocol.get_subprotocols():
            full_protocol = f"{escaped_protocol}/{sub}"
            generals = General.query.filter(General.experiment == full_protocol)
            data = {"animals": [], "experiment": sub}
            if generals.first():
                data["subprotocol"] = db.session.scalars(
                    db.select(PGeneral).where(
                        PGeneral.protocol == generals.first().experiment
                    )
                ).first()

                for general in generals:
                    animal_data = db.session.get(AnimalData, general.animal_id)
                    # Take only entries from the given year: 
                    if use_year not in animal_data.death_date: 
                        continue
                    path, _ = get_signature_path(animal_data.user)
                    signature = "default.png"
                    if path: 
                        signature = path[path.index("/")+1:] # remove `signatures/` from path
                    # Get all procedures with matching medication:
                    all_procedures = procedures(
                        Procedure.query.filter(Procedure.animal_id == animal_data.mla_num),
                        Medication.query.filter(Medication.animal_id == animal_data.mla_num),
                        Virus.query.filter(Virus.animal_id == animal_data.mla_num),
                        animal_data, 
                        num_errors
                    )
                    # Skip if start-date is not yet set or procedures are empty.
                    if not date_filled(general.start) or len(all_procedures) == 0:
                        continue
                    # Use "???" if animal's date of death is not yet set.
                    if date_filled(animal_data.death_date):
                        end_date = convert(animal_data.death_date) 
                    else:
                        end_date = "???"
                    data["animals"].append({
                        "general": general, 
                        "signature": signature, 
                        "animal_data": animal_data, 
                        "procedures": all_procedures,
                        "start": convert(general.start),
                        "end": end_date
                    })
                subprotocols[full_protocol] = data
            else: 
                print("No data for this subprotocol")
        return subprotocols, protocol.name, error_json, num_errors

    def update_dates(
        self, animal_id: str, start_date_str: str, autofill: bool,
        *, regenerate_weights: bool = True,
    ) -> str:
        """! Updates dates of experiment-data according to protocol-data. 

        @param animal_id  ID of animal 
        @param start_date_str  Start date based on which dates are filled. 

        @return message.
        """
        start_date = strtodate(start_date_str)
        # Update start-date in General
        general = db.session.get(General, animal_id)
        if general is None: 
            raise EntryNotFound(f"Animal not found + {animal_id}")
        old_start_date = general.start
        general.start = datetostr(start_date, SOURCE_DATE_FORMAT)
        if autofill is False: 
            return "Start date updated without updating other dates."
        general = db.session.get(General, animal_id)
        surgery_start = get_surgery_start(general.experiment)
        not_updated = []
        def get_date(inc):
            return datetostr(incdate(start_date, inc), SOURCE_DATE_FORMAT)
        # Update procedures: 
        for x in Procedure.query.filter(Procedure.animal_id == animal_id): 
            default = db.session.get(PProcedure, x.protocol_entry_uuid)
            if not default:
                raise EntryNotFound(
                    f"For procedure \"{x.name}\", no matching protocol-entry. "
                    + f"Delete the procedure \"{x.name}\" for this animal and add it again."
                    + "\n(This is a new functionality and was not possible before."
                    + " Sorry for the inconvenience.)",
                    400
                )
            x.start_date = get_date(int(default.days_after_start))
            x.end_date = get_date(int(default.days_after_start)+int(default.get_duration())-1)
        fill_sacrifice_date(animal_id)
        self.__update_stored(animal_id)
        if regenerate_weights and not date_filled(old_start_date):
            warning = self.try_generate_weight_list(animal_id, -1)
            if warning:
                return warning
        return "Dates where updated. Make sure to double check! " \
                f"{len(not_updated)} dates where not updated: " \
                f"{json.dumps(not_updated)}"

    def update_weights_and_watercontrol(
        self, animal_id: str, weights: str, water_control_mask: str
    ) -> None:
        """! Updates a field of in an animal entry. """
        general = db.session.get(General, animal_id)
        if general is None: 
            raise EntryNotFound(f"Animal not found + {animal_id}")
        try:
            parsed_weights = json.loads(weights)
        except (TypeError, ValueError) as error:
            raise InvalidTypeException("Weights must be a non-empty JSON list of numbers") from error
        if not isinstance(parsed_weights, list) or not parsed_weights:
            raise InvalidTypeException("Weights must be a non-empty JSON list of numbers")
        for index, weight in enumerate(parsed_weights):
            if weight is None and index > 0:
                continue  # An unmeasured day may be empty.
            try:
                finite = type(weight) in (int, float) and math.isfinite(weight)
            except OverflowError:
                finite = False
            if (not finite
                    or weight < 0 or (index == 0 and weight == 0)):
                raise InvalidTypeException("Weights must contain finite, non-negative numbers; the first weight must be positive")
        try:
            parsed_mask = json.loads(water_control_mask)
        except (TypeError, ValueError) as error:
            raise InvalidTypeException("Watercontrol must be a JSON list of booleans") from error
        if (not isinstance(parsed_mask, list) or len(parsed_mask) != len(parsed_weights)
                or any(type(value) is not bool for value in parsed_mask)):
            raise InvalidTypeException("Watercontrol must contain one boolean for each weight")
        start_weight = parse_weight(parsed_weights[0])
        general.watercontrol_mask = json.dumps(parsed_mask)
        general.weights = json.dumps(parsed_weights)
        general.set_start_weight(start_weight)
        self.__update_stored(animal_id)

    def update_definitions_entry(
        self, category: str, data: Dict[str, Any]
    ) -> None:
        """! Updates or creates new definition entry. """
        Table = get_category_table(DEFINITION_TABLES, category)
        require_entry_fields(category, data)
        # Check neccesarry fields are included:
        if "name" not in data or data["name"] == "":
            raise MissingEntryException(entry="name")
        if "/" in data["name"]:
            raise InvalidNameException(
                name=data["name"], msg="'/' not allowed for definition names!"
            )
        # Create or update entry
        original_name = data.get("original_name")
        if original_name:
            definitions_entry = db.session.get(Table, original_name)
            if definitions_entry is None:
                raise EntryNotFound("No definition found with the original name.", 404)
            validate_unchanged_name(definitions_entry, data["name"])
            definitions_entry.update(data)
        else:
            if db.session.get(Table, data["name"]) is not None:
                raise DublicateEntry("A definition with the same name already exists!")
            definitions_entry = Table.from_json(data)
            db.session.add(definitions_entry)

    def update_protocol_entry(
        self, category: str, protocol: str, data: Dict[str, Any]
    ) -> None:
        """! Updates or creates new definition entry. """
        if category not in ("general", "watercontrol"):
            get_category_table(PROTOCOL_TABLES, category)
        require_entry_fields(category, data)
        # Get protocol-entry from table definied by category
        if category == "general":
            protocol_entry = db.session.get(PGeneral, data["uuid"])
            if protocol_entry is None or protocol_entry.protocol != protocol:
                raise EntryNotFound(
                    f"No general configuration found for \"{protocol}\".", 404
                )
            protocol_entry.update(data)
            return
        if category == "watercontrol":
            protocol_entry = db.session.get(PWatercontrol, data["uuid"])
            if protocol_entry is None or protocol_entry.protocol != protocol:
                raise EntryNotFound(
                    f"No watercontrol found for \"{protocol}\".", 404
                )
            protocol_entry.update(data)
            return

        if "name" not in data or data["name"] == "---":
            raise MissingEntryException(entry="name")
        Table = get_category_table(PROTOCOL_TABLES, category)
        uuid = data.get("uuid", "")
        protocol_entry = db.session.get(Table, uuid) if uuid else None
        if uuid:
            if protocol_entry is None or protocol_entry.protocol != protocol:
                raise EntryNotFound("No entry found for this subprotocol.", 404)
        if protocol_entry is not None:
            if category == "allowed_animals":
                duplicate = Table.query.filter(
                    Table.protocol == protocol_entry.protocol,
                    Table.name == data["name"],
                    Table.uuid != protocol_entry.uuid,
                ).first()
                if duplicate is not None:
                    raise DublicateEntry("A entry with the same name already exists!")
            validate_unchanged_name(protocol_entry, data["name"])
            protocol_entry.update(data)
            return

        # otherwise, create new if not exists (not for general and watercontrol)
        if category == "medication":
            if "procedure" not in data: 
                raise MissingEntryException(entry="procedure")
            query = Table.query.filter(
                Table.protocol==protocol,
                Table.name==data["name"],
                Table.procedure==data["procedure"]
            )
        elif category == "procedures":
            if "days_after_start" not in data: 
                raise MissingEntryException(entry="days_after_start")
            query = Table.query.filter(
                Table.protocol==protocol,
                Table.name==data["name"],
                Table.days_after_start==data["days_after_start"]
            )
        else:
            query = Table.query.filter(Table.protocol==protocol, Table.name==data["name"])
        if query.first():
            raise DublicateEntry("A entry with the same name already exists!")
        protocol_entry = Table.from_form(protocol, data)
        db.session.add(protocol_entry)

    def delete_protocol_entry(self, category: str, uuid: str) -> None:
        Table = get_category_table(PROTOCOL_TABLES, category)
        protocol_entry = db.session.get(Table, uuid)
        if protocol_entry is None:
            raise EntryNotFound(f"Entry {uuid} of {category} not found!")
        db.session.delete(protocol_entry)

    def delete_definitions_entry(self, category: str, name: str) -> None:
        Table = get_category_table(DEFINITION_TABLES, category)
        definition_entry = db.session.get(Table, name)
        if definition_entry is None:
            raise EntryNotFound(f"Entry {name} of {category} not found!")
        db.session.delete(definition_entry)

    def remove_protocol(self, protocol: Protocol, escaped_protocol: str) -> None: 
        # Remove data matching this excact protocol
        self.__delete_protocol_data(escaped_protocol)
        for subprotocol in list(protocol.get_subprotocols()): 
            self.__delete_protocol_data(f"{escaped_protocol}/{subprotocol}")

        # Remove protocol.
        db.session.delete(protocol)

    def remove_subprotocol(
        self, protocol: Protocol, escaped_protocol: str, subprotocol: str
    ) -> None:
        # Remove data related to subprotocol
        self.__delete_protocol_data(f"{escaped_protocol}/{subprotocol}")
        # Remove subprotocol from protocol
        protocol.remove_subprotocol(subprotocol)

    def store_note(
        self, animal_id: str, category: str, apply_note: bool, text: str
    ) -> None: 
        """! Stores a given note under animal_id and category in database. 

        @param animal_id  ID of animal 
        @param category  Category (like general, procedures, ...)
        @param apply_note  Apply note to surgery sheet.
        @param note  The actual note
        """
        note = db.session.get(Note, (animal_id, category))
        if note:
            note.note = text
            note.surgery_sheet = apply_note
        else:
            note = Note(animal_id, category, apply_note, text) 
            db.session.add(note)

    def try_generate_weight_list(self, animal_id: str, start_weight: float) -> str | None:
        """Skip automatic generation only for known unmet prerequisites.

        The caller must commit before returning this warning as a success response.
        Unexpected failures propagate so the whole operation can roll back.
        """
        try:
            self.generate_weight_list(animal_id, start_weight)
        except WeightGenerationUnavailable as error:
            return f"Dates saved; weights were not regenerated: {error.msg}"
        return None

    def generate_weight_list(self, animal_id: str, start_weight: float) -> None:
        # Validate and calculate before changing any weight-related fields.
        general = db.session.get(General, animal_id) 
        if general is None: 
            raise EntryNotFound(f"Animal not found + {animal_id}")

        # Get animal data and watercontrol infos:
        animal_data = db.session.get(AnimalData, animal_id)
        if animal_data is None:
            raise EntryNotFound(f"Animal not found + {animal_id}")
        start_date = general.start
        if not date_filled(start_date): 
            raise WeightGenerationUnavailable("Missing start date")
        watercontrol_infos = (
            db.session.query(PWatercontrol)
            .filter_by(protocol=general.experiment)
            .first()
        )
        if watercontrol_infos is None: 
            raise WeightGenerationUnavailable(
                f"No watercontrol configuration found: {general.experiment}"
            )

        # Get some values 
        start_weight = float(start_weight) if start_weight != "" else -1
        try:
            sacrifice_date = today()
            if animal_data.death_date not in (None, "", "---"):
                sacrifice_date = strtodate(animal_data.death_date)
            start_date = strtodate(start_date)
            dob = strtodate(animal_data.dob)
        except InvalidDateException as error:
            raise WeightGenerationUnavailable(error.msg) from error
        age_at_start = (start_date - dob).days
        if age_at_start <= 0:
            raise WeightGenerationUnavailable("Start date must be after the date of birth")
        if start_date > sacrifice_date:
            raise WeightGenerationUnavailable(
                f"Start '{start_date}' is after the end date '{sacrifice_date}'"
            )
        duration = len(daterange(start_date, sacrifice_date))-1

        # Generate water-control-mask, if watercontrol is allowed:
        if watercontrol_infos.allowed:
            try:
                days_after_start = int(watercontrol_infos.days_after_start)
                water_duration = int(watercontrol_infos.duration)
            except (ValueError, TypeError) as error:
                raise WeightGenerationUnavailable(
                    "Watercontrol start and duration must be integers"
                ) from error
            if days_after_start < 0 or water_duration < 0:
                raise WeightGenerationUnavailable(
                    "Watercontrol start and duration must not be negative"
                )
            try:
                water_restriction_start = incdate(start_date, days_after_start)
                surgery_dates = get_surgery_dates(animal_id, general.experiment)
                duration_water = len(daterange(water_restriction_start, sacrifice_date))
                if duration_water > water_duration:
                    duration_water = water_duration
                if duration_water > duration:
                    duration_water = duration
            except InvalidDateException as error:
                raise WeightGenerationUnavailable(error.msg) from error
            # Calculate water-control-mask and estimated weights
            water_control_mask = get_water_control_mask(
                water_restriction_start, duration_water, surgery_dates
            )
            # Add `False`-values for days_after_start  
            days_after_start = min(duration-len(water_control_mask), days_after_start)
            water_control_mask = [False for _ in range(days_after_start-1)] + water_control_mask
            # Fill up with false values
            water_control_mask = water_control_mask + [
                False for _ in range(duration-(len(water_control_mask)-1))
            ]
        else:
            water_control_mask = [False for _ in range(duration+1)]
        # Generate estimated weights 
        estimated_weights = get_estimated_weight_list(
            age_at_start, animal_data.sex, duration, water_control_mask, start_weight
        )
        weights = apply_noise(estimated_weights, 0.070, start_weight==-1)

        # Update general data:
        general.watercontrol_mask = json.dumps(water_control_mask)
        general.weights = json.dumps(weights)
        general.set_start_weight(round(estimated_weights[0], 2))

    def update_responsible(self, old: str, new: str) -> None: 
        # First change the responsible person
        db.session.query(AnimalData).filter(AnimalData.user == old).update({AnimalData.user: new})
        # Then change the user's username
        db.session.query(User).filter_by(name=old).update({User.name: new})

    def generate_pw_reset_keys(self, email: str) -> str: 
        existing_entry = VerificationCode.query.filter_by(email=email).first()
        if existing_entry:
            # Delete the existing entry
            db.session.delete(existing_entry)

        # Create a new entry with the provided values
        priv = ''.join([ str(random.randint(0, 9)) for _ in range(8) ])
        pub = ''.join([ str(random.randint(0, 9)) for _ in range(8) ])
        new_entry = VerificationCode(email=email, priv=priv, pub=pub)
        db.session.add(new_entry)
        return priv

    def __delete_protocol_data(self, protocol: str) -> None:
        tables = [
            PGeneral,
            PWatercontrol,
            *PROTOCOL_TABLES.values()
        ]
        for Table in tables:
            entries = Table.query.filter(Table.protocol == protocol)
            # TODO (check whether entries are empty)
            for entry in entries:
                db.session.delete(entry)

    def __clear_experiment_data(self, animal_id: str) -> None:
        """! Clears experiment-data for animal

        @param animal_id  ID of animal
        """
        def delete(table):
            for x in table.query.filter(table.animal_id == animal_id):
                db.session.delete(x)
        for x in [General, Medication, Procedure, Virus]:
            delete(x)
        self.__update_stored(animal_id)

    def __load_animal_data_from_csv(
        self, path: str
    ) -> Tuple[List[str], List[str]]:
        """! Loads animal-data from CSV file.

        @param path  Path to CSV. 
        @return List of all animal-ids and list of those which where updated
        """
        # Checks whether all neccesarry keys are included.
        def check_all_keys(df: pd.DataFrame) -> bool: 
            for language_keys in self.keys_per_language.values():
                if all(key in df.keys() for key in language_keys):
                    return True
            return False
        # Load csv
        df = clevercsv.read_dataframe(path)
        if not check_all_keys(df): 
            required = " OR ".join(
                ", ".join(self.keys_per_language[language])
                for language in ("en", "de")
            )
            raise ParseException(
                f"CSV is missing required columns. Expected: {required}"
            )
        # Iterate over keys and add to data using mapping.
        updated = []
        mlas = []
        for _, row in df.iterrows():
            data = {}
            comment = ""
            for key in df.keys():
                value = row[key]
                if key in self.mapping:
                    data[self.mapping[key]] = str(value)
                    if self.mapping[key] == "protocol_pyrat":
                        for protocol in Protocol.query.all():
                            if str(value) in protocol.name:
                                data["protocol"] = protocol.name
                                data["protocol_escaped"] = escape(str(protocol.name))

            # Create or update animal-data
            animal_id = data["id"]
            mlas.append(animal_id)
            # Get comment from data and if comment should not be ignored parse it
            comment = data["comments"] if "comments" in data else ""
            # Store comment 
            comment_backup = db.session.get(CommentBackup, animal_id)
            if comment_backup:
                comment_backup.update(comment) 
            else: 
                comment_backup = CommentBackup(animal_id, comment)
                db.session.add(comment_backup)
            # Create animal data
            animal_data = db.session.get(AnimalData, animal_id)
            if animal_data:
                animal_data.update(data)
                updated.append(animal_id)
            else: 
                animal_data = AnimalData(data)
                db.session.add(animal_data)
            # Add potentially new lines
            if not db.session.get(ALine, animal_data.line): 
                line = ALine(animal_data.line)
                db.session.add(line)
            fill_sacrifice_date(animal_id)
            self.__update_stored(animal_id)
        return mlas, updated


    def __is_stored(
        self, animal_id: str, ignore_death_date: bool = False
    ) -> Tuple[int, int]:
        """! Checks if experiment-data is stored. 

        Checks if animal is dead (`death_date` is filled) and whether
        all experiment-steps are done (assuming that everything is done when
        `start` and `end` or filled)

        @param animal_id  ID of animal.
        @param ignore_death_date If True does not concider death date
        @return Boolean indicating whether data is stored or not.
        """
        dates_counter = [0, 2 if not ignore_death_date else 1] # start (and death_date)
        general = db.session.get(General, animal_id)
        if general is None: 
            return 0, 100
        dates_counter[0] += 1 if date_filled(general.start) else 0
        animal_data = db.session.get(AnimalData, animal_id)
        if not ignore_death_date:
            dates_counter[0] += 1 if date_filled(animal_data.death_date) else 0
        # Check procedures for dates
        for entry in Procedure.query.filter(Procedure.animal_id == animal_id):
            dates_counter[0] += 1 if date_filled(entry.start_date) else 0
            dates_counter[0] += 1 if date_filled(entry.end_date) else 0
            dates_counter[1] += 2 
        return dates_counter[0], dates_counter[1]

    def __update_stored(self, animal_id): 
        x, of = self.__is_stored(animal_id)
        animal_data = db.session.get(AnimalData, animal_id) 
        if animal_data is None: 
            raise EntryNotFound(f"AnimalData for {animal_id} not found")
        if x == of:
            animal_data.stored = True
        else: 
            animal_data.stored = False
        if animal_data.stored == True: 
            procedures = Procedure.query.filter(Procedure.animal_id == animal_id)
            procedures, filtered_procedures = remove_procedures_after_death(
                procedures, animal_data.death_date
            )
            animal_data.procedures_after_death = len(filtered_procedures)
            animal_data.missing_sacrifice = (
                not procedures_contains(procedures, UNEXPECTED_DEATH) and 
                not procedures_contains(procedures, "Sacrifice")
            )

def parse_weight(weight: str | float):
    try: 
        value = float(weight)
    except (ValueError, TypeError, OverflowError) as error:
        raise InvalidTypeException(f"Weight must be number: {weight}") from error
    if isinstance(weight, bool) or not math.isfinite(value) or (value <= 0 and value != -1):
        raise InvalidTypeException("Weight must be a positive finite number, or -1 for an estimate")
    return value


def get_category_table(tables, category):
    if category not in tables:
        raise EntryNotFound(f'Unknown category "{category}"')
    return tables[category]


def require_entry_fields(category, data, *, experiment=False):
    fields = {
        "medication": ("name", "kind", "procedure", "amount", "concentration", "dosis"),
        "procedures": ("name", "days_after_start", "duration", "requires_medication", "requires_virus"),
        "viruses": ("name", "procedure", "amount"),
        "kinds": ("name",), "lines": ("name",),
        "allowed_animals": ("name", "num_availible_animals"),
        "general": ("uuid", "allowed_users", "suffering"),
        "watercontrol": ("uuid", "days_after_start", "duration"),
    }
    required = fields[category]
    if experiment and category == "procedures":
        required = ("name", "start_date", "end_date", "experimenter", "protocol_entry_uuid")
    for field in required:
        if field not in data:
            raise MissingEntryException(field)

def get_surgery_start(protocol: str):
    procedures = db.session.query(PProcedure).filter_by(protocol=protocol)
    surgery_start = 900
    for procedure in procedures: 
        if procedure.surgery and int(procedure.days_after_start) < surgery_start:
            surgery_start = int(procedure.days_after_start)
    return surgery_start


def get_surgery_dates(animal_id: str, protocol: str): 
    procedures = db.session.query(Procedure).filter_by(animal_id=animal_id)
    surgery_dates = []
    for procedure in procedures:
        # Get matching protocol-entry to check if procedure is a surgery
        protocol_procedure = get_protocol_entry_by_name(PProcedure, protocol, procedure.name)
        if protocol_procedure.surgery:
            if date_filled(procedure.start_date) and date_filled(procedure.end_date):
                for date in daterange(strtodate(procedure.start_date), strtodate(procedure.end_date)):
                    surgery_dates.append(date)
    return surgery_dates

def fill_sacrifice_date(animal_id: str):
    animal_data = db.session.get(AnimalData, animal_id)
    if animal_data:
        if not date_filled(animal_data.death_date):
            return
        entries = db.session.query(Procedure).filter_by(animal_id=animal_id)
        if entries.first():
            for entry in entries: 
                template = db.session.get(PProcedure, entry.protocol_entry_uuid)
                if not template: 
                    continue
                if template and template.days_after_start == str(SACRIFICE_DATE):
                    entry.set_date(animal_data.death_date)


def validate_unchanged_name(entry, name: str):
    if name != entry.name:
        raise InvalidNameException(
            name=name, msg="The name of an existing entry cannot be changed."
        )


def get_protocol_entry_by_name(Table, protocol: str, name: str) -> Table|None:
    res = Table.query.filter(Table.protocol == protocol, Table.name == name)
    if not res.first(): 
        return None
    return res.first() 

def check_experiment_data_entry_exists(
    Table, category: str, data: Dict[str, Any], animal_id: str
) -> bool: 
    if category == "procedures": 
        return True if Table.query.filter(
            Table.animal_id == animal_id, 
            Table.name == data["name"],
            Table.start_date == data["start_date"]
        ).first() else False
    elif category == "medication":
        return True if Table.query.filter(
            Table.animal_id == animal_id, 
            Table.name == data["name"],
            Table.procedure == data["procedure"]
        ).first() else False
    elif category == "viruses":
        return True if Table.query.filter(
            Table.animal_id == animal_id, 
            Table.name == data["name"],
        ).first() else False

    else: 
        return False

def remove_procedures_after_death(
    procedures: List[Procedure], sacrifice_date: str
) -> Tuple[List[Procedure], List[Procedure]]: 
    """
    Checks if there are procedures *after* the animals death. 
    If yes, also an existing sacrice procedure es removed. Then: 
        - for score-sheet: add "unexpected death" to notes 
        - for paragraph 9: add "unexpected death" as procedure

    Returns: procedures, removed-procedure
    """
    filtered_procedures = []
    removed_procedures = []
    # Removes all procedures *after* death-date
    for p in procedures: 
        if p.start_date <= sacrifice_date:
            filtered_procedures.append(p)
        else:
            removed_procedures.append({
                "name": p.name, 
                "start_date": p.start_date, 
                "end_date": p.end_date
            })
    return filtered_procedures, removed_procedures

def procedures_contains(procedures: List[Procedure], name: str) -> bool: 
    for p in procedures: 
        if name in p.name: 
            return True 
    return False
