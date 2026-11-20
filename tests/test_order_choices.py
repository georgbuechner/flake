"""User-specific order licences, line choices and submission-time rechecks."""
import unittest

from werkzeug.exceptions import Forbidden

from data_manager.orders import get_order_licences, get_order_lines
from data_manager.tables import ALine, AnimalData, PAllowedMice, PGeneral, Protocol, User, db
from exceptions.exceptions import EntryNotFound, InvalidTypeException
from helpers import database_app


class OrderChoiceTests(unittest.TestCase):
    def setUp(self):
        self.app = database_app(self)
        self.user = User("ann@example.org", "Ann", False, "hash", b"salt")
        self.other = User("anna@example.org", "Anna", False, "hash", b"salt")
        self.zulu = Protocol("Zulu licence", "zulu", "B;A;Hidden;Unconfigured")
        self.alpha = Protocol("Alpha licence", "alpha", "Two;One;NoLines;EmptyUsers;NullUsers")
        null_users = PGeneral("alpha/NullUsers", 0, "", "Leicht")
        null_users.allowed_users = None
        db.session.add_all([
            self.user, self.other, self.zulu, self.alpha,
            PGeneral("zulu/A", 0, "Ann, Anna", "Leicht"),
            PGeneral("zulu/B", 0, " Bob,Ann , , Anna  ", "Leicht"),
            PGeneral("zulu/Hidden", 0, "Joann,Annette,Anna,ann,ann@example.org", "Leicht"),
            PGeneral("alpha/One", 0, "Ann", "Leicht"),
            PGeneral("alpha/Two", 0, "Anna", "Leicht"),
            PGeneral("alpha/NoLines", 0, "Ann", "Leicht"),
            PGeneral("alpha/EmptyUsers", 0, "", "Leicht"), null_users,
            PGeneral("missing/A", 0, "Ann", "Leicht"),
            PGeneral("alpha/Deleted", 0, "Ann", "Leicht"),
            PAllowedMice("zulu/A", "Line Z", 12),
            PAllowedMice("zulu/A", "Line A", 0),
            PAllowedMice("zulu/A", "Unspecified", None),
            PAllowedMice("zulu/B", "Other subprotocol", 4),
            PAllowedMice("alpha/One", "Other protocol", 7),
            PAllowedMice("zulu/Hidden", "Hidden line", 5),
            PAllowedMice("zulu/Unconfigured", "No permission configuration", 5),
            PAllowedMice("missing/A", "Orphan line", 5),
            PAllowedMice("alpha/Deleted", "Deleted subprotocol line", 5),
            ALine("Global line"),
            AnimalData({
                "id": "001", "sex": "m", "line": "Imported line", "dob": "2025-01-01",
                "death_date": "", "user": "Ann", "protocol_pyrat": "Zulu licence",
                "protocol_escaped": "zulu", "subprotocol": "A", "supplier": "",
            }),
        ])
        db.session.commit()

    def test_licences_match_exact_usernames_and_sort_by_display_name_and_subprotocol(self):
        choices = get_order_licences(self.user)
        self.assertEqual(choices, [
            {"licence": "alpha/NoLines", "protocol": "Alpha licence", "subprotocol": "NoLines"},
            {"licence": "alpha/One", "protocol": "Alpha licence", "subprotocol": "One"},
            {"licence": "zulu/A", "protocol": "Zulu licence", "subprotocol": "A"},
            {"licence": "zulu/B", "protocol": "Zulu licence", "subprotocol": "B"},
        ])
        self.assertEqual({option["licence"] for option in get_order_licences(self.other)},
                         {"alpha/Two", "zulu/A", "zulu/B", "zulu/Hidden"})

    def test_licence_access_requires_an_eligible_username_regardless_of_role(self):
        for name, admin, paw_control in (
            ("Nobody", False, False), ("", False, False), (" ", False, False),
            (None, False, False), ("Ann", True, False),
            ("Ann", False, True), ("Ann", True, True),
        ):
            with self.subTest(name=name, admin=admin, paw_control=paw_control):
                self.user.name, self.user.admin, self.user.paw_control = name, admin, paw_control
                licence = "zulu/Hidden" if name == "Ann" else "zulu/A"
                choices = get_order_licences(self.user)
                self.assertNotIn(licence, {choice["licence"] for choice in choices})
                if name != "Ann":
                    self.assertEqual(choices, [])
                with self.assertRaises(Forbidden):
                    get_order_lines(self.user, licence)

    def test_lines_are_scoped_to_the_selected_licence_and_keep_zero_and_unset_limits(self):
        choices = get_order_lines(self.user, "zulu/A")
        self.assertEqual(choices, [
            {"line": "Line A", "allowance": 0, "used": 0, "remaining": 0},
            {"line": "Line Z", "allowance": 12, "used": 0, "remaining": 12},
            {"line": "Unspecified", "allowance": None, "used": 0, "remaining": None},
        ])
        self.assertEqual(get_order_lines(self.user, "zulu/B"),
                         [{"line": "Other subprotocol", "allowance": 4, "used": 0, "remaining": 4}])
        self.assertEqual(get_order_lines(self.user, "alpha/NoLines"), [])

    def test_invalid_or_inaccessible_licences_cannot_load_lines(self):
        for licence, error, status in (
            ("", InvalidTypeException, 400),
            ("zulu", InvalidTypeException, 400),
            ("zulu/", InvalidTypeException, 400),
            ("/A", InvalidTypeException, 400),
            ("zulu/A/extra", InvalidTypeException, 400),
            ("missing/A", EntryNotFound, 404),
            ("alpha/Deleted", EntryNotFound, 404),
            ("zulu/Hidden", Forbidden, 403),
            ("zulu/Unconfigured", Forbidden, 403),
            ("alpha/EmptyUsers", Forbidden, 403),
            ("alpha/NullUsers", Forbidden, 403),
        ):
            with self.subTest(licence=licence):
                with self.assertRaises(error) as raised:
                    get_order_lines(self.user, licence)
                self.assertEqual(getattr(raised.exception, "status", getattr(raised.exception, "code", None)), status)

if __name__ == "__main__":
    unittest.main()
