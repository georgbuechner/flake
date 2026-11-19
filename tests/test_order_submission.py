"""Order input validation and quotas based on cumulative animal assignments."""
from datetime import date, datetime
import unittest
from unittest.mock import patch

from flask import Flask
from sqlalchemy import inspect
from werkzeug.exceptions import Forbidden

from data_manager.animal_counts import get_animal_counts
from data_manager.orders import get_order_lines, validate_order_submission
from data_manager.tables import (
    AnimalData, AnimalOrder, AnimalOrderByData, AnimalOrderById, PAllowedMice,
    PGeneral, Protocol, User, db,
)
from exceptions.exceptions import (
    EntryNotFound, FlakeError, InvalidTypeException,
    OrderAllowanceNotConfigured, OrderQuotaExceeded,
)


class OrderSubmissionTests(unittest.TestCase):
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
        clock = patch("data_manager.orders.today", return_value=datetime(2026, 11, 19, 23, 45))
        clock.start()
        self.addCleanup(clock.stop)
        self.user = User("requester@example.org", "Requester", False, "hash", b"salt")
        self.allowance = PAllowedMice("protocol/A", "Line A", 5)
        db.session.add_all([
            self.user, Protocol("Protocol", "protocol", "A;B"), Protocol("Other", "other", "A"),
            PGeneral("protocol/A", 0, "Requester, Other", "Leicht"),
            PGeneral("protocol/B", 0, "Requester", "Leicht"),
            PGeneral("other/A", 0, "Requester", "Leicht"),
            self.allowance, PAllowedMice("protocol/A", "Line B", 3),
            PAllowedMice("protocol/A", "Unspecified", None),
            PAllowedMice("protocol/A", "Zero", 0),
            PAllowedMice("protocol/B", "Line A", 20),
            PAllowedMice("other/A", "Line A", 20),
        ])
        self.add_animal("001", death_date="2020-01-01", user="Other")
        self.add_animal("002")
        self.add_animal("003", stored=True, user="Other")
        self.add_animal("004", line="Line B")
        self.add_animal("005", subprotocol="B")
        self.add_animal("006", protocol="other")
        self.add_animal("007", subprotocol="---")
        db.session.commit()
        self.data = {
            "order_type": "by_data", "licence": "protocol/A", "line": "Line A",
            "date": "2026-11-22", "sex": "unknown", "age": "8", "amount": "2",
        }
        self.ids = {
            "order_type": "by_id", "licence": "protocol/A", "line": "Line A",
            "date": "2026-11-22", "ids": ["NEW-1", "NEW-2"],
        }

    def add_animal(
        self, identifier, *, line="Line A", protocol="protocol", subprotocol="A",
        user="Requester", stored=False, death_date="",
    ):
        db.session.add(AnimalData({
            "id": identifier, "sex": "m", "line": line, "dob": "2019-01-01",
            "death_date": death_date, "user": user, "protocol_pyrat": protocol,
            "protocol_escaped": protocol, "subprotocol": subprotocol, "supplier": "",
            "stored": stored,
        }))

    def test_counts_include_all_owners_and_life_states_but_are_scoped_to_protocol_and_subprotocol(self):
        self.assertEqual(get_animal_counts("protocol", "A"), {"Line A": 3, "Line B": 1})
        self.assertEqual(get_animal_counts("protocol", "B"), {"Line A": 1})
        self.assertEqual(get_animal_counts("other", "A"), {"Line A": 1})

    def test_line_choices_report_used_and_remaining_capacity(self):
        self.assertEqual(get_order_lines(self.user, "protocol/A"), [
            {"line": "Line A", "allowance": 5, "used": 3, "remaining": 2},
            {"line": "Line B", "allowance": 3, "used": 1, "remaining": 2},
            {"line": "Unspecified", "allowance": None, "used": 0, "remaining": None},
            {"line": "Zero", "allowance": 0, "used": 0, "remaining": 0},
        ])

    def test_valid_data_order_accepts_form_integers_and_exact_remaining_capacity(self):
        order = validate_order_submission(self.user, {
            **self.data, "age": " 0 ", "amount": " 2 ", "comment": "Keep this\ncomment.",
            "user": "forged@example.org", "status": "approved", "uuid": "forged",
            "created_at": "2000-01-01",
        })
        self.assertIsInstance(order, AnimalOrderByData)
        self.assertEqual((order.age, order.amount, order.sex), (0, 2, "unknown"))
        self.assertEqual(order.date, date(2026, 11, 22))
        self.assertEqual(order.comment, "Keep this\ncomment.")
        self.assertEqual(order.user, self.user.email)
        self.assertEqual(order.status, "pending")
        self.assertNotEqual(order.uuid, "forged")
        self.assertIsInstance(order.created_at, datetime)
        self.assertTrue(inspect(order).transient)

    def test_valid_id_order_accepts_a_list_or_comma_and_whitespace_separated_text(self):
        for ids in ([" NEW-1 ", "NEW-2"], " NEW-1,\n NEW-2 ", "NEW-1\tNEW-2"):
            with self.subTest(ids=ids):
                order = validate_order_submission(self.user, {**self.ids, "ids": ids})
                self.assertIsInstance(order, AnimalOrderById)
                self.assertEqual(order.ids, ["NEW-1", "NEW-2"])
                self.assertTrue(inspect(order).transient)
        self.assertEqual(AnimalData.query.count(), 7)

    def test_both_order_modes_reject_quantities_above_remaining_capacity(self):
        for data in ({**self.data, "amount": 3}, {**self.ids, "ids": "NEW-1,NEW-2,NEW-3"}):
            with self.subTest(order_type=data["order_type"]), self.assertRaises(OrderQuotaExceeded) as raised:
                validate_order_submission(self.user, data)
            self.assertEqual(raised.exception.status, 409)
            self.assertIn("3 already assigned out of 5 allowed", raised.exception.msg)
            self.assertIn("3 requested and 2 remaining", raised.exception.msg)

    def test_zero_and_unconfigured_allowances_block_submission(self):
        for line, error in (("Zero", OrderQuotaExceeded), ("Unspecified", OrderAllowanceNotConfigured)):
            for data in (self.data, self.ids):
                with self.subTest(line=line, mode=data["order_type"]), self.assertRaises(error) as raised:
                    validate_order_submission(self.user, {**data, "line": line})
                self.assertEqual(raised.exception.status, 409)

    def test_an_already_exceeded_allowance_has_zero_remaining_and_rejects_more_orders(self):
        self.allowance.num_availible_animals = 2
        db.session.commit()
        line = next(line for line in get_order_lines(self.user, "protocol/A") if line["line"] == "Line A")
        self.assertEqual((line["used"], line["remaining"]), (3, 0))
        with self.assertRaises(OrderQuotaExceeded):
            validate_order_submission(self.user, {**self.data, "amount": 1})

    def test_counts_and_allowances_are_rechecked_for_each_submission(self):
        validate_order_submission(self.user, self.data)
        self.add_animal("008")
        db.session.commit()
        with self.assertRaises(OrderQuotaExceeded):
            validate_order_submission(self.user, self.data)
        self.allowance.num_availible_animals = 6
        db.session.commit()
        validate_order_submission(self.user, self.data)

    def test_pending_approved_and_rejected_orders_do_not_reserve_animal_places(self):
        for status in ("pending", "approved", "rejected"):
            order = AnimalOrderByData(
                licence="protocol/A", line="Line A", date=date(2026, 11, 22),
                user="other@example.org", sex="male", age=8, amount=5,
            )
            order.status = status
            db.session.add(order)
        db.session.commit()
        self.assertEqual(validate_order_submission(self.user, self.data).amount, 2)
        line = next(line for line in get_order_lines(self.user, "protocol/A") if line["line"] == "Line A")
        self.assertEqual(line["remaining"], 2)

    def test_delivery_requires_three_calendar_days_including_weekends(self):
        for value in (date(2026, 11, 22), "2026-11-22", "2026-11-23"):
            with self.subTest(date=value):
                validate_order_submission(self.user, {**self.data, "date": value})
        for value in ("2026-11-18", "2026-11-19", "2026-11-21"):
            with self.subTest(date=value), self.assertRaises(InvalidTypeException) as raised:
                validate_order_submission(self.user, {**self.data, "date": value})
            self.assertIn("2026-11-22", raised.exception.msg)

    def test_delivery_boundaries_cross_the_year_and_leap_day(self):
        for current, too_soon, minimum in (
            (datetime(2026, 12, 30), "2027-01-01", "2027-01-02"),
            (datetime(2028, 2, 27), "2028-02-29", "2028-03-01"),
        ):
            with self.subTest(today=current), patch("data_manager.orders.today", return_value=current):
                with self.assertRaises(InvalidTypeException):
                    validate_order_submission(self.user, {**self.data, "date": too_soon})
                validate_order_submission(self.user, {**self.data, "date": minimum})

    def test_malformed_dates_are_rejected(self):
        for value in (None, "", "not a date", "22.11.2026", "2026-11-31", "2027-02-29",
                      "20261122", "2026-W47-7", datetime(2026, 11, 22), True):
            with self.subTest(date=value), self.assertRaises(FlakeError) as raised:
                validate_order_submission(self.user, {**self.data, "date": value})
            self.assertEqual(raised.exception.status, 400)

    def test_required_data_fields_reject_missing_fractional_boolean_and_invalid_values(self):
        for field, values in {
            "order_type": (None, "", "other"),
            "sex": (None, "", "m", "other"),
            "age": (None, "", "-1", "1.5", 1.5, True, "1e2", str(2**63)),
            "amount": (None, "", "0", "-1", "1.5", 1.5, True, "1e2", str(2**63)),
            "comment": (None, 3, []),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(InvalidTypeException):
                    validate_order_submission(self.user, {**self.data, field: value})

    def test_empty_duplicate_and_invalid_ids_are_rejected_after_parsing(self):
        for ids in (None, [], "", " , \n ", "NEW-1, NEW-1", ["NEW-1", " NEW-1 "], [3], [None]):
            with self.subTest(ids=ids), self.assertRaises(InvalidTypeException):
                validate_order_submission(self.user, {**self.ids, "ids": ids})

    def test_an_order_cannot_combine_ids_and_data_fields(self):
        for field, value in (("sex", "male"), ("age", 0), ("amount", 2)):
            with self.subTest(field=field), self.assertRaises(InvalidTypeException):
                validate_order_submission(self.user, {**self.ids, field: value})
        with self.assertRaises(InvalidTypeException):
            validate_order_submission(self.user, {**self.data, "ids": ["NEW-1"]})
        validate_order_submission(self.user, {**self.ids, "sex": "", "age": " ", "amount": None})
        validate_order_submission(self.user, {**self.data, "ids": []})

    def test_submission_rechecks_licence_permissions_and_line_configuration(self):
        with self.assertRaises(EntryNotFound):
            validate_order_submission(self.user, {**self.data, "line": "Unconfigured line"})
        with self.assertRaises(EntryNotFound):
            validate_order_submission(self.user, {**self.data, "licence": "missing/A"})
        validate_order_submission(self.user, self.data)
        PGeneral.query.filter_by(protocol="protocol/A").one().allowed_users = "Other"
        db.session.commit()
        with self.assertRaises(Forbidden):
            validate_order_submission(self.user, self.data)

    def test_admin_and_paw_control_membership_do_not_bypass_quotas(self):
        self.user.admin = True
        self.user.paw_control = True
        db.session.commit()
        with self.assertRaises(OrderQuotaExceeded):
            validate_order_submission(self.user, {**self.data, "amount": 3})

    def test_validation_does_not_persist_orders_or_change_existing_records(self):
        before = {table.name: db.session.scalar(db.select(db.func.count()).select_from(table))
                  for table in db.metadata.sorted_tables}
        for data in (self.data, self.ids):
            self.assertTrue(inspect(validate_order_submission(self.user, data)).transient)
        with self.assertRaises(OrderQuotaExceeded):
            validate_order_submission(self.user, {**self.data, "amount": 3})
        self.assertFalse(db.session.new)
        self.assertFalse(db.session.dirty)
        db.session.commit()
        after = {table.name: db.session.scalar(db.select(db.func.count()).select_from(table))
                 for table in db.metadata.sorted_tables}
        self.assertEqual(after, before)
        self.assertEqual(AnimalOrder.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
