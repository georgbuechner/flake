"""Exercise error handling through real route and authentication decorators."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from urllib.parse import quote

from flask import Flask
from PIL import Image

from data_manager.dmanager import DManager
from data_manager.tables import (
    db, AnimalData, General, AMedication, User, CommentBackup, Virus,
    Medication, Procedure, VerificationCode,
)
from route_helpers import ROOT, load_routes


def image_bytes(image_format="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(stream, format=image_format)
    return stream.getvalue()


class RequestFailureTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / "src/templates"))
        self.app.config.update(SECRET_KEY="test-only", SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        db.init_app(self.app)
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        self.ns = load_routes(self.app, decorated=True)
        self.manager = DManager()
        self.ns["dmanager"] = self.manager
        directory = tempfile.TemporaryDirectory(prefix="flake-signature-test-")
        self.addCleanup(directory.cleanup)
        self.signatures = Path(directory.name)
        self.ns["SIGNATURE_PATH"] = directory.name
        user = User("test@example.org", "Test User", True, "unused", "unused")
        user.authenticated = True
        db.session.add(user)
        db.session.add(AnimalData({
            "id": "test", "sex": "M", "line": "Line", "dob": "2025-01-01",
            "death_date": "", "user": "Test User", "protocol_pyrat": "P", "supplier": "",
        }))
        general = General("test", "P/Sub", False, "Leicht")
        general.start_weight = 20
        general.weights = "[20, 21]"
        general.watercontrol_mask = "[false, false]"
        db.session.add(general)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = user.email
            session["_fresh"] = True
        self.ajax = {"X-Requested-With": "XMLHttpRequest"}

    def test_invalid_weight_or_mask_never_changes_existing_values(self):
        cases = [
            ('[20, "bad"]', '[false, false]'), ('[20, -1]', '[false, false]'),
            ('[20, NaN]', '[false, false]'), ('[20, Infinity]', '[false, false]'),
            ('[true, 21]', '[false, false]'), ('[0, 21]', '[false, false]'),
            ('[20, true]', '[false, false]'), ('[20, 21]', 'not JSON'),
            ('[20, 21]', '[true]'), ('[20, 21]', '[false, "false"]'),
            ('[20, 21]', 'null'), ('[20, 21]', None),
        ]
        for weights, mask in cases:
            with self.subTest(weights=weights, mask=mask):
                data = {"weights": weights}
                if mask is not None:
                    data["watercontrol"] = mask
                response = self.client.post('/update/animal_data/weights/test', data=data, headers=self.ajax)
                self.assertEqual(response.status_code, 400, response.text)
                db.session.remove()
                general = db.session.get(General, "test")
                self.assertEqual((general.start_weight, general.weights, general.watercontrol_mask),
                                 (20, '[20, 21]', '[false, false]'))

    def test_unmeasured_days_can_be_saved(self):
        response = self.client.post('/update/animal_data/weights/test', headers=self.ajax,
                                    data={"weights": "[20, null, 0]", "watercontrol": "[false, true, false]"})
        self.assertEqual(response.status_code, 200, response.text)
        db.session.remove()
        self.assertEqual(db.session.get(General, "test").weights, "[20, null, 0]")

    def test_input_pages_remain_accessible_after_saving_a_missing_final_weight(self):
        response = self.client.post('/update/animal_data/weights/test', headers=self.ajax,
                                    data={"weights": "[20, null]", "watercontrol": "[false, true]"})
        self.assertEqual(response.status_code, 200, response.text)
        for category in ('', '/medication', '/procedures', '/viruses'):
            with self.subTest(category=category):
                response = self.client.get('/animal_data/test' + category)
                self.assertEqual(response.status_code, 200, response.text)
        db.session.remove()
        self.assertEqual(db.session.get(General, "test").weights, "[20, null]")

    def test_last_weight_skips_unmeasured_days_and_preserves_decimals(self):
        for weights, expected in (([], None), ([None, 0], None), ([20, None, 0], 20),
                                  ([20, 50.9], 50.9), ([20, 50.9, None], 50.9)):
            with self.subTest(weights=weights):
                general = db.session.get(General, 'test')
                general.weights = json.dumps(weights)
                db.session.commit()
                self.assertEqual(general.get_last_measured_weight(), expected)
                response = self.client.get('/animal_data/test')
                self.assertEqual(response.status_code, 200, response.text)
                if expected is not None and expected > 50:
                    self.assertIn('Final weight is unrealistically high!', response.text)
                else:
                    self.assertNotIn('Final weight is unrealistically high!', response.text)

    def test_missing_procedure_weights_use_the_existing_start_weight_fallback(self):
        general = db.session.get(General, 'test')
        general.start = '2025-02-01'
        db.session.add(Procedure('test', 'Procedure', '2025-02-01', '2025-02-01', 'Test User'))
        db.session.flush()
        medication = Medication('test', 'Medication', 'Kind', 'Procedure', '0', '1', '1', False)
        db.session.add(medication)
        db.session.commit()
        uuid = medication.uuid
        for weight, expected_amount in ((None, '20'), (0, '20'), (30, '30')):
            with self.subTest(weight=weight):
                response = self.client.post('/update/animal_data/weights/test', headers=self.ajax,
                                            data={'weights': json.dumps([20, weight]), 'watercontrol': '[false, true]'})
                self.assertEqual(response.status_code, 200, response.text)
                db.session.remove()
                self.assertEqual(db.session.get(Medication, uuid).amount, expected_amount)

    def test_native_death_date_warning_with_subprotocol_markup_is_plain_text(self):
        payload = '<svg/onload=alert(1)>'
        animal = db.session.get(AnimalData, 'test')
        animal.protocol_escaped = 'P'
        animal.subprotocol = payload
        general = db.session.get(General, 'test')
        general.experiment = 'P/' + payload
        general.start = '2025-02-01'
        db.session.commit()
        response = self.client.post('/update/animal_data/sacrifice_date/test',
                                    headers={'Accept': 'text/html'}, data={'death_date': '2025-02-10'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content_type, 'text/plain; charset=utf-8')
        self.assertIn('Dates saved; weights were not regenerated', response.text)
        self.assertIn(payload, response.text)
        db.session.remove()
        self.assertEqual(db.session.get(AnimalData, 'test').death_date, '2025-02-10')

    def test_other_successful_warning_messages_are_plain_text(self):
        message = 'Dates saved; weights were not regenerated: <svg/onload=alert(1)>'
        with patch.object(self.manager, 'update_dates', return_value=message):
            response = self.client.post('/update/animal_data/dates/test/true',
                                        headers={'Accept': 'text/html'}, data={'start': '2025-02-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/plain; charset=utf-8')
        self.assertEqual(response.text, message)
        with patch.multiple(self.manager, set_protocol=Mock(), set_subprotocol=Mock(),
                            update_dates=Mock(), set_death_date=Mock(),
                            try_generate_weight_list=Mock(return_value=message)):
            response = self.client.post('/update/animal_data/all', headers={'Accept': 'text/html'},
                                        data={'animal_id': 'test', 'start': '2025-02-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/plain; charset=utf-8')
        self.assertEqual(response.text, message)

    def test_verification_key_deletion_success_displays_email_as_plain_text(self):
        email = '<img src=x onerror=alert(1)>@example.test'
        db.session.add(VerificationCode(email=email, priv='123', pub='456'))
        db.session.commit()
        response = self.client.post('/user_management/delete_key/' + quote(email, safe=''),
                                    headers={'Accept': 'text/html'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content_type, 'text/plain; charset=utf-8')
        self.assertIn(email, response.text)

    def test_invalid_concentrations_are_input_errors_and_edit_rolls_back(self):
        data = dict(name="Existing", kind="Kind", procedure="Procedure", amount="10", concentration="1", dosis="1")
        self.manager.update_definitions_entry("medication", data)
        db.session.commit()
        for concentration in ("0", "bad", "nan", "inf", "-1"):
            with self.subTest(concentration=concentration):
                response = self.client.post('/settings/definitions/medication', headers=self.ajax,
                                            data={**data, "original_name": "Existing", "concentration": concentration})
                self.assertEqual(response.status_code, 400, response.text)
                db.session.remove()
                self.assertEqual(db.session.get(AMedication, "Existing").concentration, "1")

    def test_unknown_categories_and_missing_protocols_are_404(self):
        for path in ('/settings/definitions/unknown', '/settings/protocols/remove/unknown',
                     '/settings/protocols/remove/unknown/sub', '/animal_data/test/unknown'):
            with self.subTest(path=path):
                response = self.client.post(path, data={"name": "Test"}, headers=self.ajax)
                self.assertEqual(response.status_code, 404, response.text)

    def test_ajax_authentication_failure_is_401_while_navigation_redirects(self):
        client = self.app.test_client()
        response = client.post('/animal_data/delete/test', headers=self.ajax, follow_redirects=True)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.mimetype, 'text/plain')
        self.assertIn('Log in', response.text)
        self.assertIsNotNone(db.session.get(AnimalData, "test"))
        response = client.get('/overview')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/login')

    def test_undecorated_page_error_is_logged_and_private_details_are_hidden(self):
        with patch.object(self.manager, 'get_current_year', side_effect=RuntimeError('private detail')):
            with self.assertLogs(self.app.logger, level='ERROR') as logs:
                response = self.client.get('/', headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, 'text/html')
        self.assertIn('The error has been logged', response.text)
        self.assertNotIn('private detail', response.text)
        self.assertIn('private detail', '\n'.join(logs.output))

    def test_native_and_ajax_errors_escape_html_and_preserve_http_headers(self):
        response = self.client.get('/missing', headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 404)
        self.assertIn('Return to FLAKE', response.text)
        payload = '<img src=x onerror="alert(1)">'
        response = self.client.get('/settings/definitions/' + payload, headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(payload, response.text)
        self.assertIn('&lt;img', response.text)
        response = self.client.get('/missing', headers={**self.ajax, "Accept": "text/html"})
        self.assertEqual(response.mimetype, 'text/plain')
        for path in ('/login', '/register'):
            response = self.client.post(path, headers={"Accept": "text/html"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.mimetype, 'text/html')
        response = self.client.put('/login', headers=self.ajax)
        self.assertEqual(response.status_code, 405)
        self.assertIn('POST', response.headers['Allow'])
        response = self.client.get('/animal_data/missing', headers=self.ajax)
        self.assertEqual(response.status_code, 404)

    def test_expected_error_rolls_back_an_earlier_bulk_delete(self):
        response = self.client.post('/animal_data/delete/test,missing', headers=self.ajax)
        self.assertEqual(response.status_code, 404)
        db.session.remove()
        self.assertIsNotNone(db.session.get(AnimalData, "test"))
        self.assertIsNotNone(db.session.get(General, "test"))

    def test_unexpected_error_rolls_back_an_earlier_bulk_delete(self):
        delete = self.manager.delete_animal_data
        def fail_second(animal_id):
            if animal_id == 'second':
                raise RuntimeError('broken')
            delete(animal_id)
        with patch.object(self.manager, 'delete_animal_data', side_effect=fail_second):
            with self.assertLogs(self.app.logger, level='ERROR'):
                response = self.client.post('/animal_data/delete/test,second', headers=self.ajax)
        self.assertEqual(response.status_code, 500)
        db.session.remove()
        self.assertIsNotNone(db.session.get(AnimalData, "test"))
        self.assertIsNotNone(db.session.get(General, "test"))

    def test_failed_subprotocol_change_restores_previous_experiment_data(self):
        animal = db.session.get(AnimalData, 'test')
        animal.protocol_escaped = 'P'
        animal.subprotocol = 'Old'
        db.session.add(Virus('test', 'Existing virus', 'Procedure', '1'))
        db.session.commit()
        response = self.client.post('/update/animal_data/subprotocol', headers=self.ajax,
                                    data={'animal_id': 'test', 'subprotocol': 'Broken', 'force': 'true'})
        self.assertEqual(response.status_code, 404, response.text)
        db.session.remove()
        self.assertEqual(db.session.get(AnimalData, 'test').subprotocol, 'Old')
        self.assertIsNotNone(db.session.get(General, 'test'))
        self.assertEqual(Virus.query.filter_by(animal_id='test').count(), 1)

    def test_invalid_csv_row_rolls_back_preceding_imported_rows(self):
        csv = (
            'ID,Responsible,Sex,DOB,Line / Strain (Name),Sacrifice date,License number,Origin\n'
            'imported,Test User,M,2025-01-01,Line,,P,Lab\n'
            'invalid,Test User,M,bad date,Line,,P,Lab\n'
        )
        response = self.client.post('/upload/pyrat_csv', headers=self.ajax,
                                    data={'csv': (io.BytesIO(csv.encode()), 'animals.csv')})
        self.assertEqual(response.status_code, 400, response.text)
        db.session.remove()
        self.assertIsNone(db.session.get(AnimalData, 'imported'))
        self.assertIsNone(db.session.get(CommentBackup, 'imported'))
        self.assertIsNotNone(db.session.get(AnimalData, 'test'))

    def test_signature_failures_preserve_original_and_remove_temporary_files(self):
        original = self.signatures / 'TestUser.png'
        original.write_bytes(image_bytes())
        for payload, mimetype in ((b'bad image', 'image/png'), (b'bad image', 'application/pdf')):
            response = self.client.post('/upload/signature/TestUser', headers=self.ajax,
                                        data={'sig': (io.BytesIO(payload), 'signature.png', mimetype)})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(original.read_bytes(), image_bytes())
            self.assertEqual(list(self.signatures.iterdir()), [original])
        for target in ('werkzeug.datastructures.FileStorage.save', 'os.replace'):
            with self.subTest(target=target):
                with patch(target, side_effect=OSError('disk failure')):
                    with self.assertLogs(self.app.logger, level='ERROR'):
                        response = self.client.post('/upload/signature/TestUser', headers=self.ajax,
                                                    data={'sig': (io.BytesIO(image_bytes()), 'signature.png', 'image/png')})
                self.assertEqual(response.status_code, 500)
                self.assertEqual(original.read_bytes(), image_bytes())
                self.assertEqual(list(self.signatures.iterdir()), [original])

    def test_signature_replacement_removes_old_format_after_success(self):
        (self.signatures / 'TestUser.jpg').write_bytes(image_bytes('JPEG'))
        response = self.client.post('/upload/signature/TestUser', headers=self.ajax,
                                    data={'sig': (io.BytesIO(image_bytes()), 'signature.png', 'image/png')})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([path.name for path in self.signatures.iterdir()], ['TestUser.png'])

    def test_administrator_ml_upload_preserves_personal_signature(self):
        personal = self.signatures / 'TestUser.png'
        personal.write_bytes(image_bytes())
        (self.signatures / 'ml-signature.jpg').write_bytes(image_bytes('JPEG'))
        uploaded = image_bytes()
        response = self.client.post('/upload/signature/ml-signature', headers=self.ajax,
                                    data={'sig': (io.BytesIO(uploaded), 'signature.png', 'image/png')})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.signatures / 'ml-signature.png').read_bytes(), uploaded)
        self.assertEqual(personal.read_bytes(), image_bytes())
        self.assertFalse((self.signatures / 'ml-signature.jpg').exists())
        response = self.client.get('/signature/ml-signature')
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        self.assertEqual(response.data, uploaded)

    def test_administrator_ml_deletion_preserves_personal_signature(self):
        personal = self.signatures / 'TestUser.png'
        personal.write_bytes(image_bytes())
        (self.signatures / 'ml-signature.png').write_bytes(image_bytes())
        response = self.client.post('/delete/signature/ml-signature', headers=self.ajax)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(personal.read_bytes(), image_bytes())
        self.assertFalse((self.signatures / 'ml-signature.png').exists())

    def test_signature_targets_are_authorized_before_any_file_changes(self):
        personal = self.signatures / 'TestUser.png'
        personal.write_bytes(image_bytes())
        ml = self.signatures / 'ml-signature.png'
        ml.write_bytes(image_bytes())
        for admin in (True, False):
            user = db.session.get(User, 'test@example.org')
            user.admin = admin
            db.session.commit()
            targets = ['OtherUser'] if admin else ['OtherUser', 'ml-signature']
            for target in targets:
                for operation in ('upload', 'delete'):
                    with self.subTest(admin=admin, target=target, operation=operation):
                        data = {'sig': (io.BytesIO(image_bytes()), 'signature.png', 'image/png')} if operation == 'upload' else {}
                        response = self.client.post(f'/{operation}/signature/{target}', headers=self.ajax, data=data)
                        self.assertEqual(response.status_code, 403, response.text)
                        self.assertEqual(personal.read_bytes(), image_bytes())
                        self.assertEqual(ml.read_bytes(), image_bytes())
                        self.assertEqual({path.name for path in self.signatures.iterdir()},
                                         {'TestUser.png', 'ml-signature.png'})

    def test_ordinary_user_can_upload_and_delete_own_signature(self):
        user = db.session.get(User, 'test@example.org')
        user.admin = False
        db.session.commit()
        ml = self.signatures / 'ml-signature.png'
        ml.write_bytes(image_bytes())
        response = self.client.post('/upload/signature/TestUser', headers=self.ajax,
                                    data={'sig': (io.BytesIO(image_bytes()), 'signature.png', 'image/png')})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((self.signatures / 'TestUser.png').read_bytes(), image_bytes())
        response = self.client.post('/delete/signature/TestUser', headers=self.ajax)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse((self.signatures / 'TestUser.png').exists())
        self.assertEqual(ml.read_bytes(), image_bytes())

    def test_missing_ml_preview_does_not_fall_back_to_a_personal_signature(self):
        (self.signatures / 'TestUser.png').write_bytes(image_bytes())
        response = self.client.get('/signature/ml-signature')
        self.assertEqual(response.status_code, 404, response.text)
        response = self.client.get('/signature/TestUser')
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
