"""Exercise routes without importing app.py's database initialization."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from data_manager.dmanager import DManager
from data_manager.tables import AnimalData, General, PProcedure, User, db
from exceptions.exceptions import InvalidTypeException, InvalidDateException
from utils.dt_utils import strtodate, SOURCE_DATE_FORMAT
from helpers import database_app, login_as
from route_helpers import load_routes


class ScoreSheetErrorTests(unittest.TestCase):
    def setUp(self):
        self.app = database_app(self)
        self.ns = load_routes(self.app, {
            "handle_exception", "user_loader", "unauthorized_handler", "generate_score_sheet",
        }, decorated=True)
        self.ns["dmanager"] = DManager()
        db.session.add_all([
            User("test@example.org", "Test", False, "hash", b"salt"),
            AnimalData({
                "id": "test", "sex": "M", "line": "Line", "dob": "2025-01-01",
                "death_date": "2025-02-01", "user": "Test",
                "protocol_pyrat": "P", "supplier": "",
            }),
            General("test", "P/Sub", False, "Leicht"),
        ])
        db.session.commit()
        self.client = self.app.test_client()
        login_as(self.client, "test@example.org")
        self.ajax = {"X-Requested-With": "XMLHttpRequest"}

    def test_missing_or_living_animals_return_plain_errors_without_logging(self):
        db.session.get(AnimalData, "test").death_date = ""
        db.session.commit()
        for animal_id, status, message in (("missing", 404, "not found"),
                                           ("test", 409, "not yet sacrificed")):
            with self.subTest(animal_id=animal_id):
                with self.assertNoLogs(self.app.logger, level="ERROR"):
                    response = self.client.get(f"/generate/score_sheet/{animal_id}", headers=self.ajax)
                self.assertEqual(response.status_code, status)
                self.assertIn(message, response.text)
                self.assertEqual(response.content_type, "text/plain; charset=utf-8")

    def test_failed_score_sheet_never_serves_file_and_removes_task(self):
        error = RuntimeError("generation failed")
        creator = Mock()
        creator.create_score_sheet.side_effect = error
        send = Mock()
        # Only replace document output; database, auth, route decorators and the
        # worker thread stay real so failures must reach the HTTP error handler.
        with patch.dict(self.ns, DCreator=Mock(return_value=creator), send_file=send):
            with self.assertLogs(self.app.logger, level="ERROR") as logs:
                response = self.client.get("/generate/score_sheet/test", headers=self.ajax)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(str(error), response.text)
        self.assertIn(str(error), "\n".join(logs.output))
        self.assertEqual(self.ns["generation_threads"], {})
        send.assert_not_called()


class InputErrorTests(unittest.TestCase):
    def test_invalid_dates_report_source_format(self):
        for value in ("invalid", None):
            with self.assertRaises(InvalidDateException) as raised:
                strtodate(value)
            self.assertEqual(raised.exception.status, 400)
            self.assertIn(SOURCE_DATE_FORMAT, raised.exception.msg)

    def test_duration_conversion_failures_are_input_errors(self):
        for duration in ("invalid", "5-2", "1-2-3", None):
            with self.subTest(duration=duration):
                with self.assertRaises(InvalidTypeException):
                    PProcedure.get_duration(SimpleNamespace(duration=duration))
        self.assertEqual(PProcedure.get_duration(SimpleNamespace(duration="3")), 3)
        self.assertEqual(PProcedure.get_duration(SimpleNamespace(duration="3-3")), 3)
