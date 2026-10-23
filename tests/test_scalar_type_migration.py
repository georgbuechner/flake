import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
import sqlalchemy as sa

from data_manager.tables import AProcedure, PProcedure, PWatercontrol, PAllowedMice, Medication


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "1bee5f4aa677"
REVISION = "e29f7b03a641"


class ScalarTypeMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="flake-scalar-migration-")
        self.addCleanup(directory.cleanup)
        url = "sqlite:///" + str(Path(directory.name) / "test.db")
        environment = patch.dict(os.environ, {"FLAKE_DATABASE_URL": url})
        environment.start()
        self.addCleanup(environment.stop)
        self.engine = sa.create_engine(url)
        self.addCleanup(self.engine.dispose)
        metadata = sa.MetaData()
        for model in (AProcedure, PProcedure, PWatercontrol, PAllowedMice, Medication):
            model.__table__.to_metadata(metadata)
        metadata.tables["availible_procedures"].c.days_after_start.type = sa.String()
        for table in ("availible_procedures", "protocol_procedures"):
            for column in ("requires_medication", "requires_virus"):
                metadata.tables[table].c[column].type = sa.Boolean()
        metadata.tables["protocol_allowed_mice"].c.name.type = sa.Integer()
        metadata.tables["medication"].c.procedure.type = sa.Integer()
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            for statement in (
                "INSERT INTO availible_procedures (name, days_after_start, duration, requires_medication, requires_virus) VALUES ('fixed', '-1', '1', 2, 1), ('unset', '---', '-', 0, 0)",
                "INSERT INTO protocol_procedures (uuid, name, days_after_start, duration, requires_medication, requires_virus) VALUES ('procedure', 'fixed', '', '1', 4, '')",
                "INSERT INTO protocol_watercontrol (uuid, protocol, allowed, days_after_start, duration) VALUES ('water', 'protocol', 0, ' ', '--')",
                "INSERT INTO protocol_allowed_mice (uuid, protocol, name, num_availible_animals) VALUES ('line', 'protocol', 'Line A', 12)",
                "INSERT INTO medication (uuid, procedure) VALUES ('medication', 'Injection')",
                "ALTER TABLE protocol_procedures ADD COLUMN legacy TEXT",
                "UPDATE protocol_procedures SET legacy = 'keep'",
                "CREATE TABLE legacy_data (value TEXT)",
                "INSERT INTO legacy_data VALUES ('keep')",
            ):
                connection.exec_driver_sql(statement)
        self.config = Config(str(ROOT / "alembic.ini"))
        command.stamp(self.config, PREVIOUS)

    def snapshot(self):
        with self.engine.connect() as connection:
            schema = connection.exec_driver_sql("SELECT type, name, sql FROM sqlite_schema ORDER BY type, name").all()
            rows = {table: connection.exec_driver_sql(f'SELECT * FROM "{table}" ORDER BY 1').all()
                    for table in sa.inspect(connection).get_table_names()}
            return schema, rows

    def test_upgrade_preserves_labels_counts_constraints_and_unrelated_data(self):
        command.upgrade(self.config, REVISION)
        with self.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                "SELECT name, days_after_start, typeof(days_after_start), duration, requires_medication FROM availible_procedures ORDER BY name"
            ).all(), [("fixed", -1, "integer", "1", 2), ("unset", None, "null", None, 0)])
            self.assertEqual(connection.exec_driver_sql(
                "SELECT days_after_start, requires_medication, requires_virus, legacy FROM protocol_procedures"
            ).one(), (None, 4, None, "keep"))
            self.assertEqual(connection.exec_driver_sql(
                "SELECT days_after_start, duration FROM protocol_watercontrol"
            ).one(), (None, None))
            self.assertEqual(connection.exec_driver_sql("SELECT name FROM protocol_allowed_mice").scalar(), "Line A")
            self.assertEqual(connection.exec_driver_sql("SELECT procedure FROM medication").scalar(), "Injection")
            self.assertEqual(connection.exec_driver_sql("SELECT value FROM legacy_data").scalar(), "keep")
            self.assertEqual(connection.exec_driver_sql("PRAGMA integrity_check").scalar(), "ok")
            for table in ("availible_procedures", "protocol_procedures"):
                columns = {column["name"]: column["type"] for column in sa.inspect(connection).get_columns(table)}
                self.assertIsInstance(columns["requires_medication"], sa.Integer)
                self.assertIsInstance(columns["requires_virus"], sa.Integer)
        for statement in (
            "INSERT INTO protocol_allowed_mice VALUES ('duplicate', 'protocol', 'Line A', 10)",
            "UPDATE protocol_allowed_mice SET num_availible_animals = -1",
        ):
            with self.assertRaises(sa.exc.IntegrityError), self.engine.begin() as connection:
                connection.exec_driver_sql(statement)

    def test_invalid_scalar_aborts_before_any_changes(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE availible_procedures SET days_after_start = 'invalid' WHERE name = 'fixed'")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Invalid integer"):
            command.upgrade(self.config, REVISION)
        self.assertEqual(self.snapshot(), before)

    def test_downgrade_refuses_lossy_conversion(self):
        command.upgrade(self.config, REVISION)
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "cannot be safely downgraded"):
            command.downgrade(self.config, PREVIOUS)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
