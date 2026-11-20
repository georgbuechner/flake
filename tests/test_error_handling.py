"""Exercise routes without importing app.py's database initialization."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from data_manager.tables import PProcedure
from exceptions.exceptions import (
    EntryNotFound, InvalidTypeException, AnimalNotSacrificed, ConfirmationRequired,
    InvalidDateException, InvalidNameException,
)
from utils.dt_utils import strtodate, SOURCE_DATE_FORMAT
from helpers import database_app
from route_helpers import load_routes


class RouteErrorTests(unittest.TestCase):
    def setUp(self):
        self.app = database_app(self)
        context = self.app.test_request_context(method="POST")
        context.push()
        self.addCleanup(context.pop)
        self.ns = load_routes(self.app, {"handle_exception", "generate_score_sheet"})

    def test_expected_errors_preserve_status_without_logging(self):
        for error in (EntryNotFound("missing"), ConfirmationRequired("confirm"),
                      InvalidNameException('<img src=x onerror="alert(1)">', "Choose another name")):
            with self.subTest(error=error):
                handler = self.ns["handle_exception"](Mock(side_effect=error))
                with self.assertNoLogs(self.app.logger, level="ERROR"):
                    response = handler()
                self.assertEqual(response.status_code, error.status)
                self.assertEqual(response.get_data(as_text=True), error.msg)
                self.assertEqual(response.content_type, "text/plain; charset=utf-8")

    def test_failed_score_sheet_never_serves_file_and_removes_task(self):
        error = RuntimeError("generation failed")
        creator = Mock()
        creator.create_score_sheet.side_effect = error
        send = Mock()
        self.ns.update(
            db=SimpleNamespace(session=Mock()), AnimalData=object,
            date_filled=lambda value: True, DCreator=Mock(return_value=creator),
            dmanager=Mock(), table_to_json=lambda value: {},
            current_user=SimpleNamespace(email="test"),
            generation_threads={}, send_file=send,
        )
        with self.assertRaises(RuntimeError) as raised:
            self.ns["generate_score_sheet"]("test")
        self.assertIs(raised.exception, error)
        self.assertEqual(self.ns["generation_threads"], {})
        send.assert_not_called()

    def test_score_sheet_missing_animal_and_incomplete_state(self):
        session = Mock()
        self.ns.update(db=SimpleNamespace(session=session), AnimalData=object,
                       date_filled=lambda value: False)
        session.get.return_value = None
        with self.assertRaises(EntryNotFound):
            self.ns["generate_score_sheet"]("missing")
        session.get.return_value = SimpleNamespace(death_date="")
        with self.assertRaises(AnimalNotSacrificed) as raised:
            self.ns["generate_score_sheet"]("alive")
        self.assertEqual(raised.exception.status, 409)


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
