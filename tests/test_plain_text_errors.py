"""Error responses are text even when user values contain HTML."""
import ast
from functools import wraps
from pathlib import Path
import unittest
from unittest.mock import Mock

from flask import Flask
from werkzeug.exceptions import HTTPException

from exceptions.exceptions import (
    FlakeError, InvalidNameException, MissingEntryException, InvalidDateException,
)
from exceptions.handlers import handle_request_error
from unittest.mock import patch


class PlainTextErrorTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.session = Mock()
        mocked_db = patch("exceptions.handlers.db", Mock(session=self.session))
        mocked_db.start()
        self.addCleanup(mocked_db.stop)
        source = Path(__file__).resolve().parents[1] / "src/app.py"
        handler = next(node for node in ast.parse(source.read_text()).body
                       if isinstance(node, ast.FunctionDef) and node.name == "handle_exception")
        namespace = {
            "wraps": wraps, "FlakeError": FlakeError, "HTTPException": HTTPException,
            "db": Mock(session=self.session), "app": self.app,
            "handle_request_error": handle_request_error,
        }
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"), namespace)
        self.handle = namespace["handle_exception"]

    def test_exception_formatting_is_plain_text_without_stripping_user_values(self):
        value = '<img src=x onerror="alert(1)">'
        self.assertEqual(InvalidNameException(value, "Invalid input").msg,
                         f"Invalid name: {value}. Invalid input")
        self.assertEqual(MissingEntryException(value).msg, f"Missing entry: {value}!")
        self.assertEqual(InvalidDateException("bad date", "YYYY-MM-DD").msg,
                         'The date "bad date" did not match any of the following formats: "YYYY-MM-DD"')

    def test_expected_error_has_plain_text_content_type(self):
        error = InvalidNameException('<script>alert(1)</script>', 'Choose another name')

        @self.handle
        def endpoint():
            raise error

        self.app.add_url_rule('/error', view_func=endpoint)
        response = self.app.test_client().get('/error')
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.content_type, 'text/plain; charset=utf-8')
        self.assertEqual(response.text, error.msg)
        self.session.rollback.assert_called_once()

    def test_unexpected_error_has_plain_text_generic_response(self):
        @self.handle
        def endpoint():
            raise RuntimeError('private details')

        self.app.add_url_rule('/error', view_func=endpoint)
        with self.assertLogs(self.app.logger, level='ERROR'):
            response = self.app.test_client().get('/error')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content_type, 'text/plain; charset=utf-8')
        self.assertNotIn('private details', response.text)
        self.session.rollback.assert_called_once()
