"""Order input validation and quotas based on cumulative animal assignments."""
from datetime import date, datetime
import unittest
from unittest.mock import patch

from sqlalchemy import inspect
from werkzeug.exceptions import Forbidden

from data_manager.animal_counts import get_animal_counts
from data_manager.orders import get_order_lines, validate_order_submission
from data_manager.tables import (
    AnimalData, AnimalOrderByData, AnimalOrderById, PAllowedMice,
    PGeneral, Protocol, User, db,
)
from exceptions.exceptions import (
    EntryNotFound, FlakeError, InvalidTypeException,
    OrderAllowanceNotConfigured, OrderQuotaExceeded,
)
from helpers import database_app


class OrderSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.app = database_app(self)
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
            PAllowedMice("protocol/B", "Foreign line", 20),
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
        line = get_order_lines(self.user, "protocol/A")[0]
        self.assertEqual((line["used"], line["remaining"]), (3, 2))

    def test_valid_data_order_accepts_form_integers_and_exact_remaining_capacity(self):
        order = validate_order_submission(self.user, {
            **self.data, "age": " 0 ", "amount": " 2 ", "comment": "Keep this\ncomment.",
        })
        self.assertIsInstance(order, AnimalOrderByData)
        self.assertEqual((order.age, order.amount, order.sex), (0, 2, "unknown"))
        self.assertEqual(order.date, date(2026, 11, 22))
        self.assertEqual(order.comment, "Keep this\ncomment.")
        self.assertTrue(inspect(order).transient)

    def test_valid_id_order_accepts_a_list_or_comma_and_whitespace_separated_text(self):
        for ids in ([" NEW-1 ", "NEW-2"], " NEW-1,\n NEW-2 ", "NEW-1\tNEW-2"):
            with self.subTest(ids=ids):
                order = validate_order_submission(self.user, {**self.ids, "ids": ids})
                self.assertIsInstance(order, AnimalOrderById)
                self.assertEqual(order.ids, ["NEW-1", "NEW-2"])

    def test_quota_boundaries_apply_to_both_order_modes(self):
        for allowance, line, quantity, error in (
            (5, "Line A", 3, OrderQuotaExceeded),
            (2, "Line A", 1, OrderQuotaExceeded), (5, "Zero", 1, OrderQuotaExceeded),
            (5, "Unspecified", 1, OrderAllowanceNotConfigured),
        ):
            self.allowance.num_availible_animals = allowance
            db.session.commit()
            for mode in ("by_data", "by_id"):
                data = ({**self.data, "amount": quantity} if mode == "by_data" else
                        {**self.ids, "ids": [f"NEW-{index}" for index in range(quantity)]})
                data["line"] = line
                with self.subTest(mode=mode, allowance=allowance, line=line, quantity=quantity), self.assertRaises(error):
                    validate_order_submission(self.user, data)
            remaining = get_order_lines(self.user, "protocol/A")[0]["remaining"]
            self.assertEqual(remaining, max(0, allowance - 3))

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

    def test_invalid_form_values_are_rejected(self):
        for field, values in {
            "order_type": (None, "", "other"),
            "sex": (None, "", "m", "other"),
            "age": (None, "", "-1", "1.5", 1.5, True, "1e2", str(2**63)),
            "amount": (None, "", "0", "-1", "1.5", 1.5, True, "1e2", str(2**63)),
            "comment": (None, 3, []),
            "date": (None, "", "not a date", "22.11.2026", "2026-11-31",
                     "20261122", "2026-W47-7", datetime(2026, 11, 22), True),
            "ids": (None, [], "", " , \n ", "NEW-1, NEW-1", ["NEW-1", " NEW-1 "], [3]),
        }.items():
            for value in values:
                data = self.ids if field == "ids" else self.data
                with self.subTest(field=field, value=value), self.assertRaises(FlakeError) as raised:
                    validate_order_submission(self.user, {**data, field: value})
                self.assertEqual(raised.exception.status, 400)

    def test_an_order_cannot_combine_ids_and_data_fields(self):
        for field, value in (("sex", "male"), ("age", 0), ("amount", 2)):
            with self.subTest(field=field), self.assertRaises(InvalidTypeException):
                validate_order_submission(self.user, {**self.ids, field: value})
        with self.assertRaises(InvalidTypeException):
            validate_order_submission(self.user, {**self.data, "ids": ["NEW-1"]})
        validate_order_submission(self.user, {**self.ids, "sex": "", "age": " ", "amount": None})
        validate_order_submission(self.user, {**self.data, "ids": []})

    def test_admin_and_paw_control_membership_do_not_bypass_quotas(self):
        self.user.admin = True
        self.user.paw_control = True
        db.session.commit()
        with self.assertRaises(OrderQuotaExceeded):
            validate_order_submission(self.user, {**self.data, "amount": 3})

    def test_submission_rechecks_permissions_and_configuration(self):
        for field, value in (("licence", "missing/A"), ("line", "Foreign line"),
                             ("line", "Unknown")):
            with self.subTest(field=field, value=value), self.assertRaises(EntryNotFound):
                validate_order_submission(self.user, {**self.data, field: value})
        for field, value in (("licence", ""), ("line", " ")):
            with self.subTest(field=field), self.assertRaises(InvalidTypeException):
                validate_order_submission(self.user, {**self.data, field: value})
        general = PGeneral.query.filter_by(protocol="protocol/A").one()
        protocol = db.session.get(Protocol, "protocol")
        for change, error in (
            (lambda: setattr(general, "allowed_users", "Other"), Forbidden),
            (lambda: db.session.delete(self.allowance), EntryNotFound),
            (lambda: setattr(protocol, "subprotocols", "B"), EntryNotFound),
            (lambda: db.session.delete(protocol), EntryNotFound),
        ):
            validate_order_submission(self.user, self.data)
            transaction = db.session.begin_nested()
            try:
                change()
                db.session.flush()
                with self.subTest(error=error), self.assertRaises(error):
                    validate_order_submission(self.user, self.data)
            finally:
                transaction.rollback()

if __name__ == "__main__":
    unittest.main()
