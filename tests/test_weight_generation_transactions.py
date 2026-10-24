"""Weight generation and date transactions against an isolated database."""
import ast
import json
import unittest
from functools import wraps
from pathlib import Path
from unittest.mock import patch

from flask import Flask, request, redirect
from werkzeug.exceptions import HTTPException

from data_manager.dmanager import DManager, parse_weight
from data_manager.tables import db, AnimalData, General, PGeneral, PWatercontrol
from exceptions.exceptions import FlakeError, InvalidTypeException, WeightGenerationUnavailable
from exceptions.handlers import handle_request_error
from utils.dt_utils import date_filled
from utils.http import text_response


class WeightGenerationTransactionTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        self.manager = DManager()
        db.session.add(AnimalData({
            'id': 'test', 'sex': 'M', 'line': 'Line', 'dob': '01.01.2025',
            'death_date': '', 'user': 'test', 'protocol_pyrat': 'protocol',
            'protocol_escaped': 'protocol', 'supplier': '', 'subprotocol': 'sub',
        }))
        general = General('test', 'protocol/sub', False, 'Leicht')
        general.start_weight = 20
        general.weights = '[20, 21]'
        general.watercontrol_mask = '[false, false]'
        db.session.add(general)
        db.session.commit()
        # Importing app.py would initialize the production database. Compile only
        # the real handlers and route bodies, and register them on this test app.
        names = {'handle_exception', 'update_animal_all', 'update_animal_death_date',
                 'update_dates', 'generate_weight_list'}
        nodes = []
        source = Path(__file__).resolve().parents[1] / 'src/app.py'
        for node in ast.parse(source.read_text()).body:
            if isinstance(node, ast.ImportFrom) and node.module == '__future__':
                nodes.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in names:
                node.decorator_list = []
                nodes.append(node)
        ns = dict(globals(), app=self.app, dmanager=self.manager)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), ns)
        for path, name in (
            ('/death/<animal_id>', 'update_animal_death_date'),
            ('/dates/<animal_id>/<autofill>', 'update_dates'),
            ('/weights/<animal_id>/<weight>', 'generate_weight_list'),
            ('/all', 'update_animal_all'),
        ):
            self.app.add_url_rule(path, view_func=ns['handle_exception'](ns[name]), methods=['POST'])
        self.client = self.app.test_client()

    def weights(self):
        db.session.remove()
        general = db.session.get(General, 'test')
        return general.start_weight, general.weights, general.watercontrol_mask

    def test_missing_start_date_preserves_death_date_and_existing_weights(self):
        response = self.client.post('/death/test', data={'death_date': '2025-02-10'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dates saved; weights were not regenerated', response.text)
        self.assertEqual(self.weights(), (20, '[20, 21]', '[false, false]'))
        self.assertEqual(db.session.get(AnimalData, 'test').death_date, '2025-02-10')

    def test_missing_configuration_preserves_new_start_date(self):
        response = self.client.post('/dates/test/true', data={'start': '2025-02-01'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('No watercontrol configuration', response.text)
        self.assertEqual(self.weights(), (20, '[20, 21]', '[false, false]'))
        self.assertEqual(db.session.get(General, 'test').start, '2025-02-01')

    def test_direct_generation_failure_is_an_error_and_keeps_start_weight(self):
        response = self.client.post('/weights/test/25')
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('saved', response.text)
        self.assertEqual(self.weights(), (20, '[20, 21]', '[false, false]'))

    def test_unexpected_generation_failure_rolls_back_dates(self):
        with patch.object(self.manager, 'generate_weight_list', side_effect=RuntimeError('broken')):
            with self.assertLogs(self.app.logger, level='ERROR'):
                response = self.client.post('/death/test', data={'death_date': '2025-02-10'})
        self.assertEqual(response.status_code, 500)
        self.weights()
        self.assertEqual(db.session.get(AnimalData, 'test').death_date, '')

    def test_calculation_failure_does_not_modify_weight_fields(self):
        general = db.session.get(General, 'test')
        general.start = '2025-02-01'
        db.session.get(AnimalData, 'test').death_date = '2025-02-10'
        db.session.add(PWatercontrol('protocol/sub', False, '0', '0'))
        db.session.commit()
        with patch('data_manager.dmanager.apply_noise', side_effect=RuntimeError('broken')):
            with self.assertRaises(RuntimeError):
                self.manager.generate_weight_list('test', 25)
        # Check before rollback, so a rollback cannot conceal premature mutations.
        self.assertEqual(general.start_weight, 20)
        self.assertEqual(general.weights, '[20, 21]')
        self.assertEqual(general.watercontrol_mask, '[false, false]')

    def test_incompatible_dates_and_invalid_config_are_known_prerequisites(self):
        general = db.session.get(General, 'test')
        general.start = '2025-02-10'
        db.session.get(AnimalData, 'test').death_date = '2025-02-01'
        control = PWatercontrol('protocol/sub', True, 'invalid', '10')
        db.session.add(control)
        db.session.commit()
        with self.assertRaises(WeightGenerationUnavailable):
            self.manager.generate_weight_list('test', 25)
        general.start = '2025-01-20'
        with self.assertRaises(WeightGenerationUnavailable):
            self.manager.generate_weight_list('test', 25)
        self.assertEqual(general.start_weight, 20)

    def test_combined_form_generates_once_after_final_dates(self):
        db.session.add(PGeneral('protocol/sub', 10, '', 'Leicht'))
        db.session.add(PWatercontrol('protocol/sub', False, '0', '0'))
        db.session.commit()
        generate = self.manager.generate_weight_list
        calls = []
        def record(animal_id, weight):
            calls.append((weight, db.session.get(General, animal_id).start,
                          db.session.get(AnimalData, animal_id).death_date))
            return generate(animal_id, weight)
        with patch.object(self.manager, 'generate_weight_list', side_effect=record):
            response = self.client.post('/all', data={
                'animal_id': 'test', 'protocol': 'protocol', 'subprotocol': 'sub',
                'start': '2025-02-01', 'end': '2025-02-10', 'start_weight': '25',
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(calls, [(25, '2025-02-01', '2025-02-10')])
        weight, weights, mask = self.weights()
        self.assertEqual(weight, 25)
        self.assertEqual(len(json.loads(weights)), 10)
        self.assertEqual(len(json.loads(mask)), 10)
