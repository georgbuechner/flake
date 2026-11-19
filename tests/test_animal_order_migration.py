"""Create and remove the orders table without changing existing application data."""
from datetime import date
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
import sqlalchemy as sa
from sqlalchemy.orm import Session

from data_manager.tables import AnimalOrder, AnimalOrderByData, AnimalOrderById


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "d6f7a21b903e"
REVISION = "f41c8d2a9b70"


class AnimalOrderMigrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="flake-animal-order-migration-")
        self.addCleanup(directory.cleanup)
        url = "sqlite:///" + str(Path(directory.name) / "test.db")
        environment = patch.dict(os.environ, {"FLAKE_DATABASE_URL": url})
        environment.start()
        self.addCleanup(environment.stop)
        self.engine = sa.create_engine(url)
        self.addCleanup(self.engine.dispose)
        # The existing schema is deliberately independent of the new model.
        metadata = sa.MetaData()
        users = sa.Table(
            "user", metadata,
            sa.Column("email", sa.String(), primary_key=True),
            sa.Column("paw_control", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        untouched = sa.Table("untouched", metadata, sa.Column("value", sa.String()))
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(users.insert(), {"email": "member@example.org", "paw_control": True})
            connection.execute(untouched.insert(), {"value": "keep"})
        self.config = Config(str(ROOT / "alembic.ini"))
        command.stamp(self.config, PREVIOUS)

    def assert_legacy_data_preserved(self):
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text('SELECT email, paw_control FROM "user"')).all(),
                             [("member@example.org", True)])
            self.assertEqual(connection.execute(sa.text("SELECT value FROM untouched")).scalar(), "keep")

    def test_upgrade_creates_the_model_schema_and_preserves_legacy_data(self):
        command.upgrade(self.config, "head")
        self.assertEqual(set(sa.inspect(self.engine).get_table_names()),
                         {"user", "untouched", "alembic_version", "animal_orders"})
        metadata = sa.MetaData()
        AnimalOrder.__table__.to_metadata(metadata)
        with self.engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={
                "compare_type": True,
                "compare_server_default": True,
                "include_object": lambda obj, name, kind, reflected, compare_to:
                    kind != "table" or name == "animal_orders",
            })
            self.assertEqual(compare_metadata(context, metadata), [])
            self.assertEqual(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar(),
                             REVISION)
        actual_checks = {constraint["name"]: constraint["sqltext"] for constraint in
                         sa.inspect(self.engine).get_check_constraints("animal_orders")}
        model_checks = {constraint.name: str(constraint.sqltext) for constraint in
                        AnimalOrder.__table__.constraints if isinstance(constraint, sa.CheckConstraint)}
        self.assertEqual(actual_checks, model_checks)
        self.assert_legacy_data_preserved()

    def test_both_models_persist_against_the_migrated_schema(self):
        command.upgrade(self.config, REVISION)
        common = {
            "licence": "protocol/subprotocol", "line": "Line A",
            "date": date(2027, 1, 15), "user": "member@example.org",
        }
        with Session(self.engine) as session:
            session.add_all([
                AnimalOrderById(**common, ids=["001", "002"]),
                AnimalOrderByData(**common, sex="unknown", age=8, amount=4),
            ])
            session.commit()
        with Session(self.engine) as session:
            orders = session.scalars(sa.select(AnimalOrder).order_by(AnimalOrder.order_type)).all()
            self.assertEqual(len(orders), 2)
            by_data, by_id = orders
            self.assertIsInstance(by_id, AnimalOrderById)
            self.assertIsInstance(by_data, AnimalOrderByData)
            self.assertEqual(by_id.ids, ["001", "002"])
            self.assertEqual((by_data.sex, by_data.age, by_data.amount), ("unknown", 8, 4))
            self.assertEqual(by_id.status, "pending")
            self.assertEqual(by_data.status, "pending")
        with self.engine.begin() as connection:
            # Database defaults cover inserts that do not go through the ORM.
            connection.execute(sa.text(
                "INSERT INTO animal_orders (uuid, order_type, licence, line, date, user, ids) "
                "VALUES ('raw', 'by_id', 'protocol/subprotocol', 'Line A', '2027-01-15', "
                "'member@example.org', '[\"003\"]')"
            ))
            row = connection.execute(sa.text(
                "SELECT status, comment, created_at FROM animal_orders WHERE uuid = 'raw'"
            )).one()
            self.assertEqual(row[:2], ("pending", ""))
            self.assertIsNotNone(row.created_at)

    def test_migrated_constraints_reject_incomplete_and_mixed_variants(self):
        command.upgrade(self.config, REVISION)
        for selection in (
            {"order_type": "other", "ids": '["001"]'},
            {"order_type": "by_id", "ids": None},
            {"order_type": "by_id", "ids": "[]"},
            {"order_type": "by_id", "ids": '["001"]', "amount": 1},
            {"order_type": "by_data", "sex": "male", "age": 8},
            {"order_type": "by_data", "sex": "male", "age": -1, "amount": 3},
            {"order_type": "by_data", "sex": "male", "age": 8, "amount": 0},
            {"order_type": "by_data", "sex": "other", "age": 8, "amount": 3},
        ):
            row = {
                "uuid": "invalid", "licence": "protocol/subprotocol", "line": "Line A",
                "date": "2027-01-15", "user": "member@example.org", "order_type": "by_id",
                "ids": None, "sex": None, "age": None, "amount": None, **selection,
            }
            with self.subTest(selection=selection), self.assertRaises(sa.exc.IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(sa.text(
                        "INSERT INTO animal_orders "
                        "(uuid, licence, line, date, user, order_type, ids, sex, age, amount) "
                        "VALUES (:uuid, :licence, :line, :date, :user, :order_type, :ids, :sex, :age, :amount)"
                    ), row)

    def test_downgrade_and_reupgrade_only_remove_order_data(self):
        command.upgrade(self.config, REVISION)
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                "INSERT INTO animal_orders (uuid, order_type, licence, line, date, user, ids) "
                "VALUES ('order', 'by_id', 'protocol/subprotocol', 'Line A', '2027-01-15', "
                "'member@example.org', '[\"001\"]')"
            ))
        command.downgrade(self.config, PREVIOUS)
        self.assertNotIn("animal_orders", sa.inspect(self.engine).get_table_names())
        self.assert_legacy_data_preserved()
        command.upgrade(self.config, REVISION)
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(sa.text("SELECT count(*) FROM animal_orders")).scalar(), 0)
        self.assert_legacy_data_preserved()


if __name__ == "__main__":
    unittest.main()
