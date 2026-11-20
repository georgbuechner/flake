"""Bulk animal copies, including date prerequisites, permissions and rollback."""
import itertools
import json
import unittest
from unittest.mock import patch

from data_manager.dmanager import DManager
from data_manager.tables import (
    db, AnimalData, General, Medication, Note, PMedication, PProcedure, PVirus,
    Procedure, Protocol, User, Virus, EXPERIMENT_TABLES,
)
from helpers import database_app, login_as
from route_helpers import load_routes


class ExperimentCopyTests(unittest.TestCase):
    def setUp(self):
        self.app = database_app(self)
        self.namespace = load_routes(self.app, decorated=True)
        self.manager = DManager()
        self.namespace["dmanager"] = self.manager
        protocol = Protocol("Protocol", "P", "")
        db.session.add(protocol)
        protocol.add_subprotocol("S")
        self.surgery = PProcedure("P/S", "Surgery", "50", "90-99", True, False, 1, 1)
        self.followup = PProcedure("P/S", "Followup", "60", "6", False, True, 0, 0)
        self.drug = PMedication("P/S", "Drug", "Kind", "Surgery", "0", "1", "2", False)
        self.fixed = PMedication("P/S", "Fixed", "Kind", "Followup", "4", "1", "1", True)
        self.virus = PVirus("P/S", "Vector", "Surgery", "2", False)
        db.session.add_all([self.surgery, self.followup, self.drug, self.fixed, self.virus])
        self.user = User("tester@example.org", "Tester", False, "unused", b"unused")
        self.user.authenticated = True
        db.session.add(self.user)
        for animal_id, start, surgery_start, surgery_end, followup, weight in (
            ("source", "2025-01-01", "2025-01-03", "2025-01-05", "2025-01-09", 10),
            ("B", "2025-02-01", "2025-02-03", "2025-02-05", "2025-02-09", 20),
            ("C", "2025-03-01", "2025-03-03", "2025-03-05", "2025-03-09", 35),
        ):
            db.session.add(AnimalData({
                "id": animal_id, "sex": "m", "line": "Line", "dob": "2024-01-01",
                "death_date": "2025-12-31", "user": "Tester", "protocol_pyrat": "P",
                "protocol_escaped": "P", "protocol": "Protocol", "subprotocol": "S", "supplier": "",
            }))
            general = General(animal_id, "P/S", True, "Leicht")
            general.start = start
            general.start_weight = weight
            general.weights = json.dumps([weight] * 12)
            general.watercontrol_mask = json.dumps([False] * 12)
            db.session.add(general)
            db.session.add_all([
                Procedure(animal_id, "Surgery", surgery_start, surgery_end,
                          "Performer" if animal_id == "source" else "Other", self.surgery.uuid),
                Procedure(animal_id, "Followup", followup, followup, "Performer", self.followup.uuid),
                Virus(animal_id, "Vector", "Surgery", "2" if animal_id == "source" else "8", self.virus.uuid),
                Note(animal_id, "general", True, "Keep this note"),
            ])
        db.session.flush()
        for animal_id in ("source", "B", "C"):
            drug = Medication(animal_id, "Drug", "Kind", "Surgery", "0", "1", "2", False,
                              toe_pinch=False, protocol_entry_uuid=self.drug.uuid)
            drug.amount = "999" if animal_id == "source" else "1"
            fixed = Medication(animal_id, "Fixed", "Kind", "Followup", "4", "1", "1", True,
                               protocol_entry_uuid=self.fixed.uuid)
            db.session.add_all([drug, fixed])
        db.session.commit()
        self.client = self.app.test_client()
        login_as(self.client, self.user.email)
        self.headers = {"X-Requested-With": "XMLHttpRequest"}

    def post(self, **changes):
        data = {"source_id": "source", "target_ids": ["B", "C"],
                "categories": ["procedures", "medication", "viruses"], "date_mode": "shift"}
        data.update(changes)
        return self.client.post("/animal_data/copy", json=data, headers=self.headers)

    def preview(self, **changes):
        data = {"source_id": "source", "target_ids": ["B", "C"]}
        data.update(changes)
        return self.client.post("/animal_data/copy/preview", json=data, headers=self.headers)

    def rows(self, Table, animal_id):
        criteria = {"mla_num": animal_id} if Table is AnimalData else {"animal_id": animal_id}
        return [{column.name: getattr(row, column.name) for column in Table.__table__.columns}
                for row in Table.query.filter_by(**criteria)]

    def snapshot(self):
        return {(Table.__tablename__, animal_id): self.rows(Table, animal_id)
                for Table in (*EXPERIMENT_TABLES.values(), General, Note, AnimalData)
                for animal_id in ("source", "B", "C")}

    def test_shift_preserves_offsets_durations_and_independent_ids(self):
        original = self.snapshot()
        response = self.post()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json["copied_rows"], 10)
        original_ids = {row["uuid"] for (table, _), rows in original.items()
                        if table in ("procedures", "medication", "virus") for row in rows}
        for animal_id, dates, amount in (("B", ("2025-02-03", "2025-02-05"), "40"),
                                         ("C", ("2025-03-03", "2025-03-05"), "70")):
            surgery = Procedure.query.filter_by(animal_id=animal_id, name="Surgery").one()
            self.assertEqual((surgery.start_date, surgery.end_date), dates)
            self.assertEqual(surgery.experimenter, "Performer")
            drug = Medication.query.filter_by(animal_id=animal_id, name="Drug").one()
            self.assertEqual(drug.amount, amount)
            self.assertFalse(drug.weight_independant)
            self.assertFalse(drug.toe_pinch)
            self.assertEqual(Medication.query.filter_by(animal_id=animal_id, name="Fixed").one().amount, "4")
            for Table in EXPERIMENT_TABLES.values():
                for row in self.rows(Table, animal_id):
                    self.assertNotIn(row["uuid"], original_ids)
                    original_ids.add(row["uuid"])
            self.assertEqual(self.rows(General, animal_id), original[("general", animal_id)])
            self.assertEqual(self.rows(Note, animal_id), original[("notes", animal_id)])
            self.assertTrue(db.session.get(AnimalData, animal_id).stored)
        for Table in EXPERIMENT_TABLES.values():
            self.assertEqual(self.rows(Table, "source"), original[(Table.__tablename__, "source")])

    def test_keep_dates_ignores_target_start_offset(self):
        response = self.post(date_mode="keep")
        self.assertEqual(response.status_code, 200, response.text)
        for animal_id in ("B", "C"):
            surgery = Procedure.query.filter_by(animal_id=animal_id, name="Surgery").one()
            self.assertEqual((surgery.start_date, surgery.end_date), ("2025-01-03", "2025-01-05"))

    def test_single_day_and_year_boundary_keep_exact_duration(self):
        surgery = Procedure.query.filter_by(animal_id="source", name="Surgery").one()
        surgery.start_date, surgery.end_date = "2024-12-31", "2025-01-02"
        db.session.commit()
        response = self.post(target_ids=["B"])
        self.assertEqual(response.status_code, 200, response.text)
        copied = Procedure.query.filter_by(animal_id="B", name="Surgery").one()
        self.assertEqual((copied.start_date, copied.end_date), ("2025-01-31", "2025-02-02"))
        followup = Procedure.query.filter_by(animal_id="B", name="Followup").one()
        self.assertEqual((followup.start_date, followup.end_date), ("2025-02-09", "2025-02-09"))

    def test_medication_only_can_keep_dates_when_target_procedures_already_match(self):
        for source in Procedure.query.filter_by(animal_id="source"):
            target = Procedure.query.filter_by(animal_id="B", name=source.name).one()
            target.start_date, target.end_date = source.start_date, source.end_date
        db.session.commit()
        before = self.rows(Procedure, "B")
        response = self.post(target_ids=["B"], categories=["medication"], date_mode="keep")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.rows(Procedure, "B"), before)
        drug = Medication.query.filter_by(animal_id="B", name="Drug").one()
        self.assertEqual((drug.amount, drug.toe_pinch), ("40", False))

    def test_every_nonempty_category_combination_replaces_only_selected_rows(self):
        for medication in Medication.query.all():
            medication.update_amount()
        db.session.commit()
        for size in range(1, 4):
            for categories in itertools.combinations(EXPERIMENT_TABLES, size):
                with self.subTest(categories=categories):
                    before = self.snapshot()
                    response = self.post(target_ids=["B"], categories=list(categories))
                    self.assertEqual(response.status_code, 200, response.text)
                    for category, Table in EXPERIMENT_TABLES.items():
                        after = self.rows(Table, "B")
                        if category in categories:
                            self.assertEqual(len(after), len(self.rows(Table, "source")))
                            self.assertTrue({r["uuid"] for r in after}.isdisjoint(
                                {r["uuid"] for r in before[(Table.__tablename__, "B")]}))
                        else:
                            self.assertEqual(after, before[(Table.__tablename__, "B")])

    def test_procedure_only_copy_recalculates_existing_medication_without_replacing_it(self):
        general = db.session.get(General, "B")
        general.weights = json.dumps([20] * 4 + [30] * 8)
        medication = Medication.query.filter_by(animal_id="B", name="Drug").one()
        medication.update_amount()
        self.assertEqual(medication.amount, "40")
        medication_id = medication.uuid
        source = Procedure.query.filter_by(animal_id="source", name="Surgery").one()
        source.start_date, source.end_date = "2025-01-05", "2025-01-07"
        db.session.commit()
        response = self.post(target_ids=["B"], categories=["procedures"])
        self.assertEqual(response.status_code, 200, response.text)
        medication = db.session.get(Medication, medication_id)
        self.assertEqual(medication.amount, "60")
        self.assertEqual(medication.procedure, "Surgery")
        self.assertEqual(Medication.query.filter_by(animal_id="B", name="Fixed").one().amount, "4")

    def test_sacrifice_procedure_uses_destination_death_date_in_both_modes(self):
        template = PProcedure("P/S", "Sacrifice", "-1", "1", False, False, 0, 0)
        db.session.add(template)
        db.session.add(Procedure("source", "Sacrifice", "2025-01-10", "2025-01-10", "Performer", template.uuid))
        db.session.get(AnimalData, "B").death_date = "2025-02-20"
        db.session.commit()
        for mode in ("shift", "keep"):
            with self.subTest(mode=mode):
                response = self.post(target_ids=["B"], categories=["procedures"], date_mode=mode)
                self.assertEqual(response.status_code, 200, response.text)
                procedure = Procedure.query.filter_by(animal_id="B", name="Sacrifice").one()
                self.assertEqual((procedure.start_date, procedure.end_date), ("2025-02-20", "2025-02-20"))

    def test_copy_preserves_edited_associations_with_and_without_source_template_ids(self):
        for Table in (Medication, Virus):
            source = Table.query.filter_by(animal_id="source", name="Drug" if Table is Medication else "Vector").one()
            data = {column.name: getattr(source, column.name) for column in Table.__table__.columns}
            data["procedure"] = "Followup"
            data.pop("weight_independant", None)
            data.pop("toe_pinch", None)
            self.manager.update_experiment_data_entry("source", "medication" if Table is Medication else "viruses", data)
        db.session.commit()
        for clear_links in (False, True):
            if clear_links:
                for Table in (Medication, Virus):
                    for entry in Table.query.filter_by(animal_id="source"):
                        entry.protocol_entry_uuid = ""
                db.session.commit()
            for cross_protocol in (False, True):
                with self.subTest(clear_links=clear_links, cross_protocol=cross_protocol):
                    if cross_protocol and db.session.get(General, "B").experiment != "P/Other":
                        if "Other" not in db.session.get(Protocol, "P").get_subprotocols():
                            self.manager.create_subprotocol("P", "Other", template=("P", "S"))
                    db.session.get(General, "B").experiment = "P/Other" if cross_protocol else "P/S"
                    db.session.commit()
                    response = self.post(target_ids=["B"])
                    self.assertEqual(response.status_code, 200, response.text)
                    for Table, Default, name in ((Medication, PMedication, "Drug"), (Virus, PVirus, "Vector")):
                        entry = Table.query.filter_by(animal_id="B", name=name).one()
                        self.assertEqual(entry.procedure, "Followup")
                        self.assertEqual(db.session.get(Default, entry.protocol_entry_uuid).procedure, "Surgery")

    def test_cross_protocol_template_mapping_uses_original_identity_when_names_repeat(self):
        self.manager.create_subprotocol("P", "Other", template=("P", "S"))
        alternate = PMedication("P/Other", "Drug", "Kind", "Followup", "0", "1", "2", False)
        db.session.add(alternate)
        db.session.get(General, "B").experiment = "P/Other"
        source = Medication.query.filter_by(animal_id="source", name="Drug").one()
        source.procedure = "Followup"
        db.session.commit()
        response = self.post(target_ids=["B"])
        self.assertEqual(response.status_code, 200, response.text)
        copied = Medication.query.filter_by(animal_id="B", name="Drug").one()
        self.assertEqual(copied.procedure, "Followup")
        self.assertEqual(db.session.get(PMedication, copied.protocol_entry_uuid).procedure, "Surgery")

    def test_medication_only_copy_matches_sacrifice_against_destination_death_date(self):
        template = PProcedure("P/S", "Sacrifice", "-1", "1", False, False, 0, 0)
        drug = PMedication("P/S", "Death drug", "Kind", "Sacrifice", "4", "1", "1", True)
        db.session.add_all([template, drug])
        for animal_id, date in (("source", "2025-01-10"), ("B", "2025-02-20")):
            db.session.add(Procedure(animal_id, "Sacrifice", date, date, "Performer", template.uuid))
            db.session.get(AnimalData, animal_id).death_date = date
        Medication.query.filter_by(animal_id="source").delete()
        db.session.add(Medication.from_default("source", drug))
        db.session.commit()
        response = self.post(target_ids=["B"], categories=["medication"], date_mode="keep")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Procedure.query.filter_by(animal_id="B", name="Sacrifice").one().start_date, "2025-02-20")

    def test_missing_experiment_start_on_source_or_any_target_aborts_entire_batch(self):
        for animal_id in ("source", "B", "C"):
            for mode in ("shift", "keep"):
                with self.subTest(animal=animal_id, mode=mode):
                    general = db.session.get(General, animal_id)
                    saved = general.start
                    general.start = ""
                    db.session.commit()
                    before = self.snapshot()
                    response = self.post(date_mode=mode)
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertIn(animal_id, response.text)
                    self.assertIn("experiment start date", response.text)
                    self.assertEqual(self.snapshot(), before)
                    general.start = saved
                    db.session.commit()

    def test_preview_shows_missing_dates_and_source_counts_without_writing(self):
        db.session.get(General, "B").start = ""
        db.session.get(AnimalData, "C").death_date = None
        db.session.commit()
        before = self.snapshot()
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json["counts"], {"procedures": 2, "medication": 2, "viruses": 1})
        self.assertEqual(response.json["source"]["start"], "2025-01-01")
        self.assertEqual(response.json["source"]["sacrifice_date"], "2025-12-31")
        self.assertEqual(response.json["targets"][0]["start"], "")
        self.assertEqual(response.json["targets"][1]["sacrifice_date"], "")
        self.assertEqual(response.json["targets"][0]["dob"], "2024-01-01")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.preview(target_ids=[]).json["targets"], [])

    def test_preview_validates_selection_and_permissions(self):
        for changes, status in (({"source_id": None}, 400), ({"target_ids": "B"}, 400),
                                ({"target_ids": [None]}, 400), ({"target_ids": ["source"]}, 400),
                                ({"target_ids": ["missing"]}, 404)):
            with self.subTest(changes=changes):
                self.assertEqual(self.preview(**changes).status_code, status)
        for animal_id in ("source", "C"):
            animal = db.session.get(AnimalData, animal_id)
            animal.user = "Other"
            db.session.commit()
            self.assertEqual(self.preview().status_code, 403)
            animal.user = "Tester"
            db.session.commit()
        self.assertEqual(self.client.post("/animal_data/copy/preview", json=[], headers=self.headers).status_code, 400)

    def test_entered_dates_are_applied_with_rows_in_both_modes(self):
        template = PProcedure("P/S", "Sacrifice", "-1", "1", False, False, 0, 0)
        db.session.add(template)
        db.session.add(Procedure("source", "Sacrifice", "2025-01-15", "2025-01-15", "Performer", template.uuid))
        for mode in ("shift", "keep"):
            with self.subTest(mode=mode):
                db.session.get(General, "B").start = ""
                db.session.get(AnimalData, "B").death_date = None
                db.session.commit()
                weights = db.session.get(General, "B").weights
                response = self.post(target_ids=["B"], date_mode=mode,
                                     target_dates={"B": {"start": "2025-03-01", "sacrifice_date": "2025-03-20"}})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(db.session.get(General, "B").start, "2025-03-01")
                self.assertEqual(db.session.get(AnimalData, "B").death_date, "2025-03-20")
                self.assertEqual(db.session.get(General, "B").weights, weights)
                surgery = Procedure.query.filter_by(animal_id="B", name="Surgery").one()
                self.assertEqual(surgery.start_date, "2025-03-03" if mode == "shift" else "2025-01-03")
                sacrifice = Procedure.query.filter_by(animal_id="B", name="Sacrifice").one()
                self.assertEqual((sacrifice.start_date, sacrifice.end_date), ("2025-03-20", "2025-03-20"))

    def test_source_dates_can_be_used_and_skipped_animals_are_completely_unchanged(self):
        for animal_id in ("B", "C"):
            db.session.get(General, animal_id).start = ""
            db.session.get(AnimalData, animal_id).death_date = ""
        db.session.commit()
        before = self.snapshot()
        response = self.post(target_dates={"B": {"start": "2025-01-01", "sacrifice_date": "2025-12-31"}},
                             skip_ids=["C", "C"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json["target_ids"], ["B"])
        self.assertEqual(response.json["skipped_ids"], ["C"])
        self.assertEqual(response.json["copied_rows"], 5)
        self.assertEqual(db.session.get(General, "B").start, "2025-01-01")
        self.assertEqual(db.session.get(AnimalData, "B").death_date, "2025-12-31")
        for key, value in before.items():
            if key[1] in ("source", "C"):
                self.assertEqual(self.snapshot()[key], value)

    def test_missing_sacrifice_date_requires_entry_or_skipping(self):
        db.session.get(AnimalData, "C").death_date = ""
        db.session.commit()
        before = self.snapshot()
        response = self.post()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("sacrifice date", response.text)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.post(skip_ids=["C"]).status_code, 200)

    def test_invalid_or_overwritten_date_choices_reject_the_whole_batch(self):
        for choices in ([], {"missing": {}}, {"B": []}, {"B": {"start": None}},
                        {"B": {"other": "2025-01-01"}}, {"B": {"start": "2025-02-02"}}):
            with self.subTest(choices=choices):
                before = self.snapshot()
                self.assertEqual(self.post(target_dates=choices).status_code, 400)
                self.assertEqual(self.snapshot(), before)
        for skip_ids in ("C", [None], ["source"], ["missing"]):
            before = self.snapshot()
            self.assertEqual(self.post(skip_ids=skip_ids).status_code, 400)
            self.assertEqual(self.snapshot(), before)
        db.session.get(General, "C").start = ""
        db.session.get(AnimalData, "C").death_date = ""
        db.session.commit()
        for start, end in (("", "2025-05-01"), ("2025-02-30", "2025-05-01"),
                           ("2023-12-31", "2025-05-01"), ("2025-06-01", "2025-05-01"),
                           ("9999-12-31", "9999-12-31")):
            before = self.snapshot()
            response = self.post(target_dates={"C": {"start": start, "sacrifice_date": end}})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(self.snapshot(), before)

    def test_entering_sacrifice_date_updates_linked_procedure_without_replacing_it(self):
        template = PProcedure("P/S", "Sacrifice", "-1", "1", False, False, 0, 0)
        drug = PMedication("P/S", "Death drug", "Kind", "Sacrifice", "4", "1", "1", True)
        db.session.add_all([template, drug])
        db.session.add(Procedure("source", "Sacrifice", "2025-01-10", "2025-01-10", "Performer", template.uuid))
        destination = Procedure("B", "Sacrifice", "", "", "Other", template.uuid)
        db.session.add(destination)
        Medication.query.filter_by(animal_id="source").delete()
        db.session.add(Medication.from_default("source", drug))
        db.session.get(AnimalData, "B").death_date = ""
        db.session.commit()
        destination_id = destination.uuid
        response = self.post(target_ids=["B"], categories=["medication"],
                             target_dates={"B": {"sacrifice_date": "2025-02-20"}})
        self.assertEqual(response.status_code, 200, response.text)
        destination = db.session.get(Procedure, destination_id)
        self.assertEqual((destination.start_date, destination.end_date), ("2025-02-20", "2025-02-20"))
        self.assertEqual(destination.experimenter, "Other")
        self.assertEqual(db.session.get(AnimalData, "B").death_date, "2025-02-20")

    def test_write_failure_rolls_back_entered_dates_and_first_animal_rows(self):
        from data_manager.experiment_copy import apply_experiment_copy
        for animal_id in ("B", "C"):
            db.session.get(General, animal_id).start = ""
            db.session.get(AnimalData, animal_id).death_date = ""
        db.session.commit()
        before = self.snapshot()

        def fail_second(plan):
            apply_experiment_copy(plan)
            if plan.animal_id == "C":
                raise RuntimeError("Failed after setting dates")

        dates = {animal_id: {"start": "2025-01-01", "sacrifice_date": "2025-12-31"} for animal_id in ("B", "C")}
        with patch("data_manager.dmanager.apply_experiment_copy", side_effect=fail_second):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.post(target_dates=dates)
        self.assertEqual(response.status_code, 500)
        db.session.remove()
        self.assertEqual(self.snapshot(), before)

    def test_missing_invalid_or_reversed_source_dates_abort_without_writes(self):
        for start, end in (("", "2025-01-05"), ("2025-01-03", ""), ("1", "2025-01-05"),
                           ("2025-02-30", "2025-03-01"), ("2025-01-09", "2025-01-05")):
            with self.subTest(start=start, end=end):
                row = Procedure.query.filter_by(animal_id="source", name="Surgery").one()
                row.start_date, row.end_date = start, end
                db.session.commit()
                before = self.snapshot()
                response = self.post()
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("Surgery", response.text)
                self.assertEqual(self.snapshot(), before)

    def test_medication_and_viruses_require_matching_existing_procedure_dates(self):
        for mode in ("shift", "keep"):
            row = Procedure.query.filter_by(animal_id="C", name="Surgery").one()
            row.end_date = "2025-03-06"
            db.session.commit()
            before = self.snapshot()
            response = self.post(categories=["medication", "viruses"], date_mode=mode)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("Include procedures", response.text)
            self.assertEqual(self.snapshot(), before)

    def test_invalid_requests_are_rejected(self):
        for changes in ({"source_id": None}, {"target_ids": []}, {"target_ids": "B"},
                        {"target_ids": [None]}, {"target_ids": ["source"]},
                        {"categories": []}, {"categories": "procedures"},
                        {"categories": ["general"]}, {"categories": [{}]}, {"date_mode": "other"}):
            with self.subTest(changes=changes):
                before = self.snapshot()
                response = self.post(**changes)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(self.snapshot(), before)
        for data in ([], None, "source"):
            response = self.client.post("/animal_data/copy", data=json.dumps(data),
                                        content_type="application/json", headers=self.headers)
            self.assertEqual(response.status_code, 400, response.text)

    def test_duplicate_ids_and_categories_are_deduplicated(self):
        response = self.post(target_ids=["B", "B"], categories=["procedures", "procedures"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json["target_ids"], ["B"])
        self.assertEqual(response.json["copied_rows"], 2)

    def test_permissions_checked_for_source_and_every_target(self):
        for animal_id in ("source", "C"):
            animal = db.session.get(AnimalData, animal_id)
            animal.user = "Other"
            db.session.commit()
            before = self.snapshot()
            response = self.post()
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(self.snapshot(), before)
            self.user.admin = True
            db.session.commit()
            self.assertEqual(self.post().status_code, 200)
            self.user.admin = False
            animal.user = "Tester"
            db.session.commit()

    def test_missing_animal_or_general_rejects_whole_batch(self):
        for changes in ({"source_id": "missing"}, {"target_ids": ["B", "missing"]}):
            before = self.snapshot()
            response = self.post(**changes)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(self.snapshot(), before)
        db.session.delete(db.session.get(General, "C"))
        db.session.commit()
        before = self.snapshot()
        self.assertEqual(self.post().status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_login_required(self):
        before = self.snapshot()
        client = self.app.test_client()
        for path in ("/animal_data/copy", "/animal_data/copy/preview"):
            with self.subTest(path=path):
                response = client.post(path, json={}, headers=self.headers)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(self.snapshot(), before)

    def test_cross_subprotocol_copy_remaps_template_ids(self):
        self.manager.create_subprotocol("P", "Other", template=("P", "S"))
        db.session.get(General, "B").experiment = "P/Other"
        db.session.get(AnimalData, "B").subprotocol = "Other"
        db.session.commit()
        response = self.post(target_ids=["B"])
        self.assertEqual(response.status_code, 200, response.text)
        for Table, Default in ((Procedure, PProcedure), (Medication, PMedication), (Virus, PVirus)):
            for row in Table.query.filter_by(animal_id="B"):
                self.assertEqual(db.session.get(Default, row.protocol_entry_uuid).protocol, "P/Other")

    def test_missing_or_ambiguous_destination_template_aborts(self):
        self.manager.create_subprotocol("P", "Other", template=("P", "S"))
        db.session.get(General, "C").experiment = "P/Other"
        db.session.add(PProcedure("P/Other", "Surgery", "2", "3", True, False, 0, 0))
        db.session.commit()
        before = self.snapshot()
        response = self.post()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("no unique procedures", response.text)
        self.assertEqual(self.snapshot(), before)
        PProcedure.query.filter_by(protocol="P/Other", name="Surgery").delete()
        db.session.commit()
        response = self.post()
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.snapshot(), before)

    def test_procedure_copy_cannot_leave_unselected_entries_without_a_procedure(self):
        Procedure.query.filter_by(animal_id="source", name="Followup").delete()
        db.session.commit()
        before = self.snapshot()
        response = self.post(categories=["procedures"])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Followup", response.text)
        self.assertEqual(self.snapshot(), before)

    def test_empty_selected_category_and_missing_source_links_abort(self):
        Virus.query.filter_by(animal_id="source").delete()
        db.session.commit()
        before = self.snapshot()
        response = self.post(categories=["viruses"])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.snapshot(), before)
        Procedure.query.filter_by(animal_id="source", name="Surgery").delete()
        db.session.commit()
        before = self.snapshot()
        response = self.post(categories=["medication"])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.snapshot(), before)

    def test_repeated_procedure_names_keep_individual_offsets_and_durations(self):
        db.session.add(Procedure("source", "Surgery", "2025-01-12", "2025-01-15", "Performer", self.surgery.uuid))
        db.session.commit()
        response = self.post(categories=["procedures"])
        self.assertEqual(response.status_code, 200, response.text)
        dates = {(row.start_date, row.end_date) for row in Procedure.query.filter_by(animal_id="B", name="Surgery")}
        self.assertEqual(dates, {("2025-02-03", "2025-02-05"), ("2025-02-12", "2025-02-15")})

    def test_copy_and_paste_modes_render_on_all_overviews(self):
        for path in ("/animal_data/source", "/overview", "/users/Tester", "/protocols/P"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                if path == "/animal_data/source":
                    self.assertNotIn('/static/js/experiment_copy.js', response.text)
                else:
                    self.assertIn('/static/js/experiment_copy.js', response.text)
                    self.assertIn('id="experiment-copy-mode"', response.text)
                    self.assertIn('id="experiment-paste-mode"', response.text)
                    for category in ("procedures", "viruses", "medication"):
                        self.assertIn(f'name="copy_category" value="{category}"', response.text)
                    self.assertIn('id="open-experiment-paste"', response.text)
                    self.assertIn('value="shift"', response.text)
                    self.assertIn('value="keep"', response.text)


if __name__ == "__main__":
    unittest.main()
