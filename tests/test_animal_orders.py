"""Persistence and invariants for the two variants of an animal order."""
from datetime import date, datetime, timezone
import unittest
import uuid

from flask import Flask
from sqlalchemy.exc import IntegrityError, InvalidRequestError

from data_manager.tables import (
    AnimalData, AnimalOrder, AnimalOrderByData, AnimalOrderById, db, table_to_json,
)
from exceptions.exceptions import InvalidTypeException


class AnimalOrderTests(unittest.TestCase):
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
        self.common = {
            "licence": "protocol/subprotocol", "line": "Line A",
            "date": date(2027, 1, 15), "user": "requester@example.org",
        }

    def test_both_variants_round_trip_through_one_table_and_a_shared_query(self):
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        by_id = AnimalOrderById(**self.common, ids=["001", "MLA-002"], comment="Requested IDs")
        by_data = AnimalOrderByData(**self.common, sex="female", age=8, amount=3)
        self.assertEqual(by_id.status, "pending")
        self.assertEqual(by_data.status, "pending")
        self.assertNotEqual(by_id.uuid, by_data.uuid)
        self.assertEqual(str(uuid.UUID(by_id.uuid)), by_id.uuid)
        db.session.add_all([by_id, by_data])
        db.session.commit()
        identifiers = by_id.uuid, by_data.uuid
        db.session.remove()

        orders = {order.uuid: order for order in AnimalOrder.query.all()}
        self.assertEqual(len(orders), 2)
        by_id, by_data = (orders[identifier] for identifier in identifiers)
        self.assertIsInstance(by_id, AnimalOrderById)
        self.assertIsInstance(by_data, AnimalOrderByData)
        self.assertEqual(by_id.ids, ["001", "MLA-002"])
        self.assertEqual((by_data.sex, by_data.age, by_data.amount), ("female", 8, 3))
        self.assertEqual(by_id.comment, "Requested IDs")
        self.assertEqual(by_data.comment, "")
        for order in orders.values():
            for key, value in self.common.items():
                self.assertEqual(getattr(order, key), value)
            self.assertLessEqual(before, order.created_at)
            self.assertLessEqual(order.created_at, datetime.now(timezone.utc).replace(tzinfo=None))
            self.assertEqual(order.status, "pending")
        self.assertEqual(table_to_json(by_id)["ids"], ["001", "MLA-002"])
        self.assertEqual(table_to_json(by_data)["amount"], 3)
        self.assertEqual(AnimalOrderById.query.count(), 1)
        self.assertEqual(AnimalOrderByData.query.count(), 1)
        self.assertEqual(AnimalData.query.count(), 0)
        self.assertIs(AnimalOrderById.__table__, AnimalOrder.__table__)
        self.assertIs(AnimalOrderByData.__table__, AnimalOrder.__table__)

    def test_shared_base_cannot_be_instantiated(self):
        with self.assertRaises(InvalidRequestError):
            AnimalOrder(**self.common)

    def test_ids_are_normalized_copied_and_can_be_replaced(self):
        original = [" 001 ", "MLA-002"]
        order = AnimalOrderById(**self.common, ids=original)
        original.append("not part of the order")
        self.assertEqual(order.ids, ["001", "MLA-002"])
        db.session.add(order)
        db.session.commit()
        identifier = order.uuid
        order.ids = [*order.ids, "MLA-003"]
        db.session.commit()
        db.session.remove()
        self.assertEqual(db.session.get(AnimalOrder, identifier).ids, ["001", "MLA-002", "MLA-003"])

    def test_invalid_id_lists_are_rejected(self):
        for ids in (None, [], "001,002", [1], [None], [""], [" "], ["001", " 001 "]):
            with self.subTest(ids=ids), self.assertRaises(InvalidTypeException):
                AnimalOrderById(**self.common, ids=ids)

    def test_data_requires_a_supported_sex_and_integer_age_and_amount(self):
        valid = {"sex": "unknown", "age": 0, "amount": 1}
        for sex in ("female", "male", "unknown"):
            db.session.add(AnimalOrderByData(**self.common, **{**valid, "sex": sex}))
        db.session.commit()
        self.assertEqual(AnimalOrder.query.count(), 3)
        for key, values in {
            "sex": (None, "", "m", "other"),
            "age": (None, -1, 1.5, "8", True, 2**63),
            "amount": (None, 0, -1, 1.5, "3", True, 2**63),
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(InvalidTypeException):
                    AnimalOrderByData(**self.common, **{**valid, key: value})

    def test_required_order_fields_and_status_are_validated_on_assignment(self):
        for key in ("licence", "line", "user"):
            for value in (None, "", " "):
                with self.subTest(key=key, value=value), self.assertRaises(InvalidTypeException):
                    AnimalOrderById(**{**self.common, key: value}, ids=["001"])
        for value in (None, "2027-01-15", datetime(2027, 1, 15)):
            with self.subTest(date=value), self.assertRaises(InvalidTypeException):
                AnimalOrderById(**{**self.common, "date": value}, ids=["001"])
        order = AnimalOrderById(**self.common, ids=["001"])
        for status in ("pending", "approved", "rejected"):
            order.status = status
            db.session.add(order)
            db.session.commit()
        with self.assertRaises(InvalidTypeException):
            order.status = "ordered"

    def test_database_rejects_invalid_selection_shapes_and_values(self):
        by_id = AnimalOrderById(**self.common, ids=["001"])
        by_data = AnimalOrderByData(**self.common, sex="male", age=8, amount=3)
        db.session.add_all([by_id, by_data])
        db.session.commit()
        by_id_uuid, by_data_uuid = by_id.uuid, by_data.uuid
        invalid_changes = (
            (by_id_uuid, {"order_type": "other"}),
            (by_id_uuid, {"status": "ordered"}),
            (by_id_uuid, {"ids": None}),
            (by_id_uuid, {"ids": []}),
            (by_id_uuid, {"ids": "001"}),
            (by_id_uuid, {"sex": "male"}),
            (by_id_uuid, {"order_type": "by_data"}),
            (by_data_uuid, {"ids": ["001"]}),
            (by_data_uuid, {"sex": None}),
            (by_data_uuid, {"sex": "other"}),
            (by_data_uuid, {"age": None}),
            (by_data_uuid, {"age": -1}),
            (by_data_uuid, {"age": 1.5}),
            (by_data_uuid, {"amount": None}),
            (by_data_uuid, {"amount": 0}),
            (by_data_uuid, {"amount": -1}),
            (by_data_uuid, {"amount": 1.5}),
        )
        for identifier, changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(IntegrityError):
                    db.session.execute(
                        AnimalOrder.__table__.update().where(AnimalOrder.uuid == identifier).values(**changes)
                    )
                    db.session.commit()
                db.session.rollback()
        self.assertEqual(AnimalOrder.query.count(), 2)


if __name__ == "__main__":
    unittest.main()
