"""Exercise routes without importing app.py's database initialization."""
import ast
import io
import json
import tempfile
import unittest
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image
from werkzeug.datastructures import FileStorage

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from data_manager.dmanager import DManager
from data_manager.tables import db, General, PProcedure
from document_creator.dcreator import GenerationThread
from exceptions.exceptions import (
    FlakeError, EntryNotFound, InvalidTypeException, MissingEntryException,
    AnimalNotSacrificed, ConfirmationRequired, InvalidDateException,
)
from utils.dt_utils import strtodate, SOURCE_DATE_FORMAT
from route_helpers import load_routes as load_app_routes


def load_routes(app):
    return load_app_routes(app, {
        "handle_exception", "upload_signature", "generate_score_sheet",
    })


class RouteErrorTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db.init_app(self.app)
        context = self.app.test_request_context(method="POST")
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        self.ns = load_routes(self.app)

    def test_expected_errors_preserve_status_without_logging(self):
        for error in (EntryNotFound("missing"), ConfirmationRequired("confirm")):
            with self.subTest(error=error):
                handler = self.ns["handle_exception"](Mock(side_effect=error))
                with self.assertNoLogs(self.app.logger, level="ERROR"):
                    response = handler()
                self.assertEqual(response.status_code, error.status)
                self.assertEqual(response.get_data(as_text=True), error.msg)

    def test_framework_bad_request_is_preserved(self):
        @self.ns["handle_exception"]
        def endpoint():
            return request.form["missing"]
        with self.app.test_request_context(method="POST"):
            with self.assertNoLogs(self.app.logger, level="ERROR"):
                response = endpoint()
        self.assertEqual(response.status_code, 400)

    def test_unexpected_error_is_logged_but_not_exposed(self):
        @self.ns["handle_exception"]
        def endpoint():
            raise RuntimeError("private detail")
        with self.assertLogs(self.app.logger, level="ERROR") as logs:
            response = endpoint()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private detail", response.get_data(as_text=True))
        self.assertIn("RuntimeError: private detail", "\n".join(logs.output))

    def test_signature_upload_validates_before_removing_existing_file(self):
        remove = Mock()
        self.ns.update(remove_signature_if_present=remove, current_user=SimpleNamespace(name="test"))
        with self.app.test_request_context(method="POST"):
            with self.assertRaises(MissingEntryException):
                self.ns["upload_signature"]("test")
        remove.assert_not_called()

    def test_first_signature_upload_does_not_require_existing_signature(self):
        stream = io.BytesIO()
        Image.new("RGB", (2, 2), "white").save(stream, format="PNG")
        stream.seek(0)
        directory = tempfile.TemporaryDirectory(prefix="flake-signature-test-")
        self.addCleanup(directory.cleanup)
        self.ns.update(
            request=SimpleNamespace(files={"sig": FileStorage(stream, "signature.png", content_type="image/png")}),
            current_user=SimpleNamespace(name="test"),
            SIGNATURE_PATH=directory.name,
        )
        self.assertEqual(self.ns["upload_signature"]("test"), ("", 200))
        with Image.open(Path(directory.name) / "test.png") as image:
            self.assertEqual(image.format, "PNG")
        self.assertEqual([path.name for path in Path(directory.name).iterdir()], ["test.png"])

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

    def test_invalid_weight_payloads_do_not_update_general(self):
        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db.init_app(app)
        with app.app_context():
            db.create_all()
            general = General("test", "protocol/sub", False, "Leicht")
            db.session.add(general)
            db.session.commit()
            manager = DManager()
            for weights in (None, "bad", "[]", "{}", "null", '["bad"]', '[null]'):
                with self.subTest(weights=weights):
                    with self.assertRaises(InvalidTypeException):
                        manager.update_weights_and_watercontrol("test", weights, "[true]")
                    self.assertEqual(general.weights, "[]")
                    self.assertEqual(general.watercontrol_mask, "[]")
            db.session.remove()
            db.engine.dispose()
