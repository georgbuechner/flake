"""User-specific order licences, line choices and submission-time rechecks."""
import json
import unittest

from flask import Flask
from werkzeug.exceptions import Forbidden

from data_manager.orders import get_order_licences, get_order_lines, validate_order_selection
from data_manager.tables import ALine, AnimalData, PAllowedMice, PGeneral, Protocol, User, db
from exceptions.exceptions import EntryNotFound, InvalidTypeException


class OrderChoiceTests(unittest.TestCase):
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
        self.assertEqual(json.loads(json.dumps(choices)), choices)

    def test_users_without_permissions_including_blank_names_have_no_choices(self):
        for name in ("Nobody", "", " ", None):
            with self.subTest(name=name):
                self.user.name = name
                self.assertEqual(get_order_licences(self.user), [])
                with self.assertRaises(Forbidden):
                    get_order_lines(self.user, "zulu/A")

    def test_admin_and_paw_control_membership_do_not_bypass_licence_permissions(self):
        for admin, paw_control in ((True, False), (False, True), (True, True)):
            with self.subTest(admin=admin, paw_control=paw_control):
                self.user.admin = admin
                self.user.paw_control = paw_control
                self.assertNotIn("zulu/Hidden", {option["licence"] for option in get_order_licences(self.user)})
                with self.assertRaises(Forbidden):
                    get_order_lines(self.user, "zulu/Hidden")
                with self.assertRaises(Forbidden):
                    validate_order_selection(self.user, "zulu/Hidden", "Hidden line")

    def test_lines_are_scoped_to_the_selected_licence_and_keep_zero_and_unset_limits(self):
        choices = get_order_lines(self.user, "zulu/A")
        self.assertEqual(choices, [
            {"line": "Line A", "allowance": 0},
            {"line": "Line Z", "allowance": 12},
            {"line": "Unspecified", "allowance": None},
        ])
        self.assertEqual(get_order_lines(self.user, "zulu/B"),
                         [{"line": "Other subprotocol", "allowance": 4}])
        self.assertEqual(get_order_lines(self.user, "alpha/NoLines"), [])
        self.assertEqual(json.loads(json.dumps(choices)), choices)

    def test_missing_licences_and_permissions_are_rejected_by_both_selection_helpers(self):
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
                with self.assertRaises(error):
                    validate_order_selection(self.user, licence, "Line Z")

    def test_selection_rejects_lines_from_other_licences_or_without_an_allowance_row(self):
        for line in ("Other subprotocol", "Other protocol", "Global line", "Imported line", "Unknown"):
            with self.subTest(line=line), self.assertRaises(EntryNotFound):
                validate_order_selection(self.user, "zulu/A", line)
        for line in ("", " "):
            with self.subTest(line=line), self.assertRaises(InvalidTypeException):
                validate_order_selection(self.user, "zulu/A", line)
        for line, allowance in (("Line Z", 12), ("Line A", 0), ("Unspecified", None)):
            row = validate_order_selection(self.user, "zulu/A", line)
            self.assertEqual((row.protocol, row.name, row.num_availible_animals), ("zulu/A", line, allowance))

    def test_submission_rechecks_revoked_permissions(self):
        get_order_licences(self.user)
        get_order_lines(self.user, "zulu/A")
        general = PGeneral.query.filter_by(protocol="zulu/A").one()
        general.allowed_users = "Anna"
        db.session.commit()
        self.assertNotIn("zulu/A", {option["licence"] for option in get_order_licences(self.user)})
        with self.assertRaises(Forbidden):
            validate_order_selection(self.user, "zulu/A", "Line Z")

    def test_submission_rechecks_deleted_line_configurations(self):
        get_order_lines(self.user, "zulu/A")
        db.session.delete(PAllowedMice.query.filter_by(protocol="zulu/A", name="Line Z").one())
        db.session.commit()
        with self.assertRaises(EntryNotFound):
            validate_order_selection(self.user, "zulu/A", "Line Z")

    def test_submission_rechecks_deleted_protocols_and_subprotocols_despite_orphan_configurations(self):
        get_order_lines(self.user, "zulu/A")
        self.zulu.subprotocols = "B;Hidden;Unconfigured"
        db.session.commit()
        with self.assertRaises(EntryNotFound):
            validate_order_selection(self.user, "zulu/A", "Line Z")
        self.assertNotIn("zulu/A", {option["licence"] for option in get_order_licences(self.user)})
        get_order_lines(self.user, "zulu/B")
        db.session.delete(self.zulu)
        db.session.commit()
        with self.assertRaises(EntryNotFound):
            validate_order_selection(self.user, "zulu/B", "Other subprotocol")
        self.assertFalse(any(option["licence"].startswith("zulu/") for option in get_order_licences(self.user)))

    def test_choice_queries_and_selection_checks_do_not_write_database_records(self):
        before = {table.name: db.session.scalar(db.select(db.func.count()).select_from(table))
                  for table in db.metadata.sorted_tables}
        get_order_licences(self.user)
        get_order_lines(self.user, "zulu/A")
        validate_order_selection(self.user, "zulu/A", "Line Z")
        self.assertFalse(db.session.new)
        self.assertFalse(db.session.dirty)
        db.session.commit()
        after = {table.name: db.session.scalar(db.select(db.func.count()).select_from(table))
                 for table in db.metadata.sorted_tables}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
