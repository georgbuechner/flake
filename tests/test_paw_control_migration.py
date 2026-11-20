import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "e29f7b03a641"
REVISION = "d6f7a21b903e"


class PawControlMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="flake-paw-control-migration-")
        self.addCleanup(directory.cleanup)
        url = "sqlite:///" + str(Path(directory.name) / "test.db")
        environment = patch.dict(os.environ, {"FLAKE_DATABASE_URL": url})
        environment.start()
        self.addCleanup(environment.stop)
        self.engine = sa.create_engine(url)
        self.addCleanup(self.engine.dispose)
        metadata = sa.MetaData()
        # Define the old schema independently of the updated ORM model.
        users = sa.Table(
            "user", metadata,
            sa.Column("email", sa.String(), primary_key=True),
            sa.Column("name", sa.String()),
            sa.Column("admin", sa.Boolean()),
            sa.Column("password", sa.String()),
            sa.Column("salt", sa.String()),
            sa.Column("authenticated", sa.Boolean()),
        )
        untouched = sa.Table("untouched", metadata, sa.Column("value", sa.String()))
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(users.insert(), [
                {"email": "admin@example.org", "name": "Admin", "admin": True,
                 "password": "admin-hash", "salt": "admin-salt", "authenticated": True},
                {"email": "user@example.org", "name": "User", "admin": False,
                 "password": "user-hash", "salt": "user-salt", "authenticated": False},
            ])
            connection.execute(untouched.insert(), {"value": "keep"})
        self.config = Config(str(ROOT / "alembic.ini"))
        command.stamp(self.config, PREVIOUS)

    def legacy_rows(self):
        with self.engine.connect() as connection:
            return connection.execute(sa.text(
                "SELECT email, name, admin, password, salt, authenticated "
                'FROM "user" ORDER BY email'
            )).all()

    def test_upgrade_backfills_all_users_and_preserves_existing_data(self):
        before = self.legacy_rows()
        command.upgrade(self.config, "head")
        self.assertEqual(self.legacy_rows(), before)
        column = next(column for column in sa.inspect(self.engine).get_columns("user")
                      if column["name"] == "paw_control")
        self.assertIsInstance(column["type"], sa.Boolean)
        self.assertFalse(column["nullable"])
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text(
                'SELECT paw_control FROM "user" ORDER BY email'
            )).scalars().all(), [False, False])
            self.assertEqual(connection.execute(sa.text("SELECT value FROM untouched")).scalar(), "keep")
            self.assertEqual(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar(),
                             REVISION)

    def test_database_defaults_new_users_to_false_and_rejects_null(self):
        command.upgrade(self.config, REVISION)
        with self.engine.begin() as connection:
            connection.execute(sa.text('INSERT INTO "user" (email) VALUES (\'new@example.org\')'))
            self.assertEqual(connection.execute(sa.text(
                'SELECT paw_control FROM "user" WHERE email = \'new@example.org\''
            )).scalar(), False)
        with self.assertRaises(sa.exc.IntegrityError), self.engine.begin() as connection:
            connection.execute(sa.text('UPDATE "user" SET paw_control = NULL'))

    def test_downgrade_and_reupgrade_preserve_legacy_data(self):
        before = self.legacy_rows()
        command.upgrade(self.config, REVISION)
        with self.engine.begin() as connection:
            connection.execute(sa.text('UPDATE "user" SET paw_control = 1'))
        command.downgrade(self.config, PREVIOUS)
        self.assertNotIn("paw_control", [column["name"] for column in sa.inspect(self.engine).get_columns("user")])
        self.assertEqual(self.legacy_rows(), before)
        self.assertEqual(sa.inspect(self.engine).get_pk_constraint("user")["constrained_columns"], ["email"])
        command.upgrade(self.config, REVISION)
        self.assertEqual(self.legacy_rows(), before)
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text('SELECT paw_control FROM "user"')).scalars().all(),
                             [False, False])


if __name__ == "__main__":
    unittest.main()
