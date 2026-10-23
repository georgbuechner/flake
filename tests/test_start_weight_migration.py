import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
import sqlalchemy as sa

from data_manager.tables import General


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "c38f0257d914"
REVISION = "1bee5f4aa677"


class StartWeightMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="flake-weight-migration-")
        self.addCleanup(directory.cleanup)
        url = "sqlite:///" + str(Path(directory.name) / "test.db")
        environment = patch.dict(os.environ, {"FLAKE_DATABASE_URL": url})
        environment.start()
        self.addCleanup(environment.stop)
        self.engine = sa.create_engine(url)
        self.addCleanup(self.engine.dispose)
        metadata = sa.MetaData()
        table = General.__table__.to_metadata(metadata)
        table.c.start_weight.type = sa.Integer()
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(table.insert(), [
                {"animal_id": "fractional", "start_weight": 23.75},
                {"animal_id": "whole", "start_weight": 24},
                {"animal_id": "estimated", "start_weight": -1},
                {"animal_id": "missing", "start_weight": None},
            ])
            connection.execute(sa.text("CREATE TABLE untouched (value TEXT)"))
            connection.execute(sa.text("INSERT INTO untouched VALUES ('keep')"))
        self.config = Config(str(ROOT / "alembic.ini"))
        command.stamp(self.config, PREVIOUS)

    def rows(self):
        with self.engine.connect() as connection:
            return connection.execute(sa.text("SELECT * FROM general ORDER BY animal_id")).all()

    def column_type(self):
        return next(column["type"] for column in sa.inspect(self.engine).get_columns("general")
                    if column["name"] == "start_weight")

    def test_upgrade_preserves_data_and_unrelated_tables(self):
        before = self.rows()
        command.upgrade(self.config, REVISION)
        self.assertIsInstance(self.column_type(), sa.Float)
        self.assertEqual(self.rows(), before)
        self.assertEqual(sa.inspect(self.engine).get_pk_constraint("general")["constrained_columns"],
                         ["animal_id"])
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text("SELECT value FROM untouched")).scalar(), "keep")

    def test_downgrade_refuses_to_truncate_fractional_weights(self):
        command.upgrade(self.config, REVISION)
        before = self.rows()
        with self.assertRaisesRegex(RuntimeError, "fractional weights"):
            command.downgrade(self.config, PREVIOUS)
        self.assertIsInstance(self.column_type(), sa.Float)
        self.assertEqual(self.rows(), before)
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar(),
                             REVISION)

    def test_whole_weights_can_downgrade_and_upgrade(self):
        with self.engine.begin() as connection:
            connection.execute(sa.text("UPDATE general SET start_weight = 23 WHERE animal_id = 'fractional'"))
        before = self.rows()
        command.upgrade(self.config, REVISION)
        command.downgrade(self.config, PREVIOUS)
        self.assertIsInstance(self.column_type(), sa.Integer)
        self.assertEqual(self.rows(), before)
        command.upgrade(self.config, REVISION)
        self.assertEqual(self.rows(), before)


if __name__ == "__main__":
    unittest.main()
