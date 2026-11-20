"""Schedule ranged protocol offsets through subprotocol changes and date autofill."""
from datetime import timedelta
import unittest
from unittest.mock import patch

from data_manager.dmanager import DManager, get_surgery_dates
from data_manager.tables import AnimalData, General, PProcedure, Procedure, Protocol, User, db
from exceptions.exceptions import InvalidTypeException
from helpers import database_app, login_as
from route_helpers import load_routes
from utils.dt_utils import strtodate


class ProcedureSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.app = database_app(self)
        self.manager = DManager()
        namespace = load_routes(self.app, {
            "handle_exception", "user_loader", "unauthorized_handler",
            "update_animal_subprotocol", "update_dates",
        }, decorated=True)
        namespace["dmanager"] = self.manager
        protocol = Protocol("Protocol", "P", "")
        db.session.add(protocol)
        protocol.add_subprotocol("2A")
        protocol.add_subprotocol("2B")
        user = User("tester@example.org", "Tester", True, "unused", b"unused")
        user.authenticated = True
        db.session.add_all([
            user,
            AnimalData({
                "id": "animal", "sex": "M", "line": "Line", "dob": "2025-01-01",
                "death_date": "2025-04-10", "user": "Tester", "protocol_pyrat": "Protocol",
                "protocol_escaped": "P", "subprotocol": "2A", "supplier": "",
            }),
            General("animal", "P/2A", False, "Leicht"),
            Procedure("animal", "Old procedure", "2025-02-01", "2025-02-01", "Tester"),
        ])
        # The five ranged offsets from G0146_21/2B, plus fixed and sacrifice offsets.
        self.templates = {}
        for name, offset, duration, surgery in (
            ("Viral injection", "0-6", "1", True),
            ("Post-surgery habituation", "6-10", "2-4", False),
            ("Behavioral training", "8-13", "7-11", False),
            ("Craniotomy", "20-25", "1", True),
            ("Electrophysiological recording", "21-26", "2-4", False),
            ("Pre-surgery habituation", "-3", "3", False),
            ("Headpost implant", "0", "1", True),
            ("Sacrifice", "-1", "1", False),
        ):
            template = PProcedure("P/2B", name, offset, duration, surgery, False, 0, 0)
            self.templates[name] = template
            db.session.add(template)
        # An unused optional surgery must not prevent scheduling the actual procedures.
        db.session.add(PProcedure("P/2B", "Optional surgery", None, None, True, True, 0, 0))
        db.session.commit()
        self.client = self.app.test_client()
        login_as(self.client, user.email)
        self.ajax = {"X-Requested-With": "XMLHttpRequest"}

    def switch_subprotocol(self, subprotocol="2B"):
        response = self.client.post("/update/animal_data/subprotocol", headers=self.ajax, data={
            "animal_id": "animal", "subprotocol": subprotocol, "force": "true",
        })
        self.assertEqual(response.status_code, 200, response.text)
        db.session.remove()

    def procedures(self):
        return {row.name: row for row in Procedure.query.filter_by(animal_id="animal")}

    def autofill(self, start):
        self.manager.update_dates("animal", start, True, regenerate_weights=False)
        db.session.commit()
        db.session.remove()

    def test_switch_then_autofill_schedules_all_ranges_and_sacrifices(self):
        self.switch_subprotocol()
        self.assertEqual(db.session.get(AnimalData, "animal").subprotocol, "2B")
        self.assertEqual(db.session.get(General, "animal").experiment, "P/2B")
        rows = self.procedures()
        self.assertEqual(set(rows), set(self.templates))
        for name in list(self.templates)[:5]:
            self.assertEqual((rows[name].start_date, rows[name].end_date), ("", ""))
        self.assertEqual(rows["Sacrifice"].start_date, "2025-04-10")

        # Exercise the real date route, including subsequent weight generation.
        response = self.client.post("/update/animal_data/dates/animal/true",
                                    headers=self.ajax, data={"start": "2025-02-01"})
        self.assertEqual(response.status_code, 200, response.text)
        db.session.remove()
        rows = self.procedures()
        start = strtodate("2025-02-01")
        for name, lower, upper, min_duration, max_duration in (
            ("Viral injection", 0, 6, 1, 1),
            ("Post-surgery habituation", 6, 10, 2, 4),
            ("Behavioral training", 8, 13, 7, 11),
            ("Craniotomy", 20, 25, 1, 1),
            ("Electrophysiological recording", 21, 26, 2, 4),
        ):
            with self.subTest(name=name):
                row = rows[name]
                offset = (strtodate(row.start_date) - start).days
                duration = (strtodate(row.end_date) - strtodate(row.start_date)).days + 1
                self.assertTrue(lower <= offset <= upper, offset)
                self.assertTrue(min_duration <= duration <= max_duration, duration)
        self.assertEqual((rows["Pre-surgery habituation"].start_date,
                          rows["Pre-surgery habituation"].end_date),
                         ("2025-01-29", "2025-01-31"))
        self.assertEqual(rows["Headpost implant"].start_date, "2025-02-01")
        self.assertEqual((rows["Sacrifice"].start_date, rows["Sacrifice"].end_date),
                         ("2025-04-10", "2025-04-10"))
        self.assertCountEqual(get_surgery_dates("animal", "P/2B"), [
            strtodate(rows[name].start_date)
            for name in ("Viral injection", "Craniotomy", "Headpost implant")
        ])

    def test_changing_start_date_preserves_selected_offsets_across_requests(self):
        self.switch_subprotocol()
        self.autofill("2025-02-01")
        dates = {name: row.start_date for name, row in self.procedures().items()}
        self.autofill("2025-02-01")
        self.assertEqual({name: row.start_date for name, row in self.procedures().items()}, dates)
        self.autofill("2025-03-01")
        for name, row in self.procedures().items():
            with self.subTest(name=name):
                if name == "Sacrifice":
                    self.assertEqual(row.start_date, dates[name])
                else:
                    self.assertEqual(strtodate(row.start_date),
                                     strtodate(dates[name]) + timedelta(days=28))

    def test_offset_is_chosen_again_when_the_protocol_range_changes(self):
        self.switch_subprotocol()
        self.autofill("2025-02-01")
        template = PProcedure.query.filter_by(name="Viral injection").one()
        template.days_after_start = "10-12"
        db.session.commit()
        self.autofill("2025-02-01")
        offset = (strtodate(self.procedures()["Viral injection"].start_date)
                  - strtodate("2025-02-01")).days
        self.assertTrue(10 <= offset <= 12, offset)

    def test_repeated_procedure_names_use_their_own_offset_ranges(self):
        # G0332_19/E has three training entries with separate scheduling windows.
        db.session.get(Protocol, "P").add_subprotocol("E")
        for offset in ("0-3", "7-8", "9-10"):
            db.session.add(PProcedure("P/E", "Behavioral training", offset, "1",
                                      False, False, 0, 0))
        db.session.commit()
        self.switch_subprotocol("E")
        self.autofill("2025-02-01")
        offsets = sorted((strtodate(row.start_date) - strtodate("2025-02-01")).days
                         for row in Procedure.query.filter_by(animal_id="animal"))
        self.assertEqual(len(offsets), 3)
        self.assertTrue(0 <= offsets[0] <= 3)
        self.assertTrue(7 <= offsets[1] <= 8)
        self.assertTrue(9 <= offsets[2] <= 10)

    def test_negative_range_is_scheduled_relative_to_the_experiment_start(self):
        template = self.templates["Viral injection"]
        template.days_after_start = "-5--3"
        db.session.commit()
        self.switch_subprotocol()
        self.autofill("2025-02-01")
        offset = (strtodate(self.procedures()["Viral injection"].start_date)
                  - strtodate("2025-02-01")).days
        self.assertTrue(-5 <= offset <= -3, offset)

    def test_existing_manual_date_within_the_range_is_preserved(self):
        self.switch_subprotocol()
        general = db.session.get(General, "animal")
        general.start = "2025-02-01"
        injection = self.procedures()["Viral injection"]
        injection.set_date("2025-02-05")
        db.session.commit()
        db.session.remove()
        self.autofill("2025-03-01")
        injection = self.procedures()["Viral injection"]
        self.assertEqual((injection.start_date, injection.end_date),
                         ("2025-03-05", "2025-03-05"))

    def test_invalid_offset_rolls_back_the_subprotocol_change(self):
        template = PProcedure.query.filter_by(name="Viral injection").one()
        template.days_after_start = "6-0"
        db.session.commit()
        response = self.client.post("/update/animal_data/subprotocol", headers=self.ajax, data={
            "animal_id": "animal", "subprotocol": "2B", "force": "true",
        })
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Invalid start offset", response.text)
        db.session.remove()
        self.assertEqual(db.session.get(AnimalData, "animal").subprotocol, "2A")
        self.assertEqual(db.session.get(General, "animal").experiment, "P/2A")
        self.assertEqual(set(self.procedures()), {"Old procedure"})

    def test_offset_parser_handles_inclusive_bounds_and_signed_offsets(self):
        template = self.templates["Viral injection"]
        for text, bounds in (("0-6", (0, 6)), (" -5--3 ", (-5, -3)),
                             ("-3-2", (-3, 2)), ("-1", (-1, -1)),
                             ("0", (0, 0)), ("3-3", (3, 3))):
            with self.subTest(text=text):
                template.days_after_start = text
                self.assertEqual(template.get_start_offset_bounds(), bounds)
        template.days_after_start = "0-6"
        for boundary in (0, 6):
            with patch("data_manager.tables.random.randint", return_value=boundary) as choose:
                self.assertEqual(template.get_start_offset(), boundary)
                choose.assert_called_once_with(0, 6)
            with patch("data_manager.tables.random.randint") as choose:
                self.assertEqual(template.get_start_offset(boundary), boundary)
                choose.assert_not_called()
        for text in (None, "6-0", "0-6-9", "1.5", "2025-02-01", "abc"):
            with self.subTest(text=text):
                template.days_after_start = text
                with self.assertRaises(InvalidTypeException):
                    template.get_start_offset()


if __name__ == "__main__":
    unittest.main()
