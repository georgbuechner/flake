import unittest

from flask import Flask

from data_manager.dmanager import DManager
from data_manager.tables import (
    db, AnimalData, DEFINITION_TABLES, PROTOCOL_TABLES, EXPERIMENT_TABLES,
)
from exceptions.exceptions import DublicateEntry, EntryNotFound, InvalidNameException


class DefinitionNameTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        db.init_app(app)
        context = app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        self.manager = DManager()
        self.data = {
            "name": "Original", "uuid": "", "procedure": "Procedure", "kind": "Kind",
            "amount": "10", "concentration": "1", "dosis": "1", "weight_independant": "on",
            "days_after_start": "1", "duration": "2", "requires_medication": 0,
            "requires_virus": 0, "start_date": "2025-01-01", "end_date": "2025-01-02",
            "experimenter": "Test", "protocol_entry_uuid": "",
        }

    def test_global_definitions_reject_rename_and_duplicate_add(self):
        for category, Table in DEFINITION_TABLES.items():
            with self.subTest(category=category):
                self.manager.update_definitions_entry(category, self.data)
                with self.assertRaises(DublicateEntry):
                    self.manager.update_definitions_entry(category, self.data)
                with self.assertRaises(InvalidNameException):
                    self.manager.update_definitions_entry(category, {
                        **self.data, "original_name": "Original", "name": "Renamed",
                    })
                self.manager.update_definitions_entry(category, {
                    **self.data, "original_name": "Original", "amount": "20",
                })
                self.assertIsNone(db.session.get(Table, "Renamed"))
                self.assertEqual(Table.query.count(), 1)
                if hasattr(Table, "amount"):
                    self.assertEqual(db.session.get(Table, "Original").amount, "20")

    def test_global_definition_edit_does_not_recreate_deleted_entry(self):
        with self.assertRaises(EntryNotFound):
            self.manager.update_definitions_entry("viruses", {
                **self.data, "original_name": "Original",
            })

    def test_protocol_names_locked_but_other_values_editable(self):
        self.manager.update_definitions_entry("procedures", self.data)
        for category in ("medication", "procedures", "viruses"):
            with self.subTest(category=category):
                self.manager.update_protocol_entry(category, "protocol/sub", self.data)
                row = PROTOCOL_TABLES[category].query.one()
                data = {**self.data, "uuid": row.uuid}
                with self.assertRaises(InvalidNameException):
                    self.manager.update_protocol_entry(category, "protocol/sub", {
                        **data, "name": "Renamed",
                    })
                with self.assertRaises(EntryNotFound):
                    self.manager.update_protocol_entry(category, "protocol/other", data)
                with self.assertRaises(EntryNotFound):
                    self.manager.update_protocol_entry(category, "protocol/sub", {
                        **data, "uuid": "missing",
                    })
                self.manager.update_protocol_entry(category, "protocol/sub", {
                    **data, "amount": "20", "duration": "3",
                })
                self.assertEqual(row.name, "Original")
                self.assertEqual(row.duration if category == "procedures" else row.amount,
                                 "3" if category == "procedures" else "20")

    def test_animal_names_locked_but_other_values_editable(self):
        db.session.add(AnimalData({
            "id": "animal", "sex": "m", "line": "Line", "dob": "2025-01-01",
            "death_date": "", "user": "Test", "protocol_pyrat": "protocol", "supplier": "",
        }))
        db.session.commit()
        for category in ("medication", "procedures", "viruses"):
            with self.subTest(category=category):
                self.manager.update_experiment_data_entry("animal", category, self.data)
                row = EXPERIMENT_TABLES[category].query.one()
                data = {**self.data, "uuid": row.uuid}
                with self.assertRaises(InvalidNameException):
                    self.manager.update_experiment_data_entry("animal", category, {
                        **data, "name": "Renamed",
                    })
                with self.assertRaises(EntryNotFound):
                    self.manager.update_experiment_data_entry("another-animal", category, data)
                self.manager.update_experiment_data_entry("animal", category, {
                    **data, "amount": "20", "experimenter": "Another experimenter",
                })
                self.assertEqual(row.name, "Original")
                self.assertEqual(row.experimenter if category == "procedures" else row.amount,
                                 "Another experimenter" if category == "procedures" else "20")


if __name__ == "__main__":
    unittest.main()
