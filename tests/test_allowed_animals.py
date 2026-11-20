import unittest
from html.parser import HTMLParser

from sqlalchemy.exc import IntegrityError

from data_manager.dmanager import DManager
from data_manager.tables import db, PAllowedMice, ALine, AnimalData, Protocol, User
from exceptions.exceptions import DublicateEntry, InvalidTypeException, InvalidNameException, EntryNotFound
from helpers import database_app, login_as
from route_helpers import load_routes


class AllowanceRows(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows = []
        self.row = {}
        self.cell = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = attrs
        elif tag == "td" and attrs.get("name") == "num_availible_animals":
            self.cell = attrs
            self.cell["text"] = ""
            self.rows.append((self.row, attrs))

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag):
        if tag == "td":
            self.cell = None


class AllowedAnimalTests(unittest.TestCase):
    def setUp(self):
        self.app = database_app(self)
        self.manager = DManager()
        self.first = PAllowedMice("protocol/sub", "Line A", 10)
        self.second = PAllowedMice("protocol/sub", "Line B", 20)
        db.session.add_all([self.first, self.second])
        db.session.commit()

    def update(self, uuid, name, allowance="30", protocol="protocol/sub"):
        self.manager.update_protocol_entry("allowed_animals", protocol, {
            "uuid": uuid, "name": name, "num_availible_animals": allowance,
        })
        db.session.commit()

    def test_duplicate_edit_rejected_without_changing_existing_row(self):
        with self.assertRaises(DublicateEntry) as raised:
            self.update(self.second.uuid, "Line A")
        self.assertEqual(raised.exception.status, 409)
        db.session.expire_all()
        self.assertEqual(self.second.name, "Line B")
        self.assertEqual(self.second.num_availible_animals, 20)

    def test_edit_own_allowance_but_reject_renaming(self):
        self.update(self.first.uuid, "Line A")
        self.assertEqual(self.first.num_availible_animals, 30)
        with self.assertRaises(InvalidNameException):
            self.update(self.first.uuid, "Line C")
        self.assertEqual(self.first.name, "Line A")

    def test_edit_rejects_wrong_subprotocol_and_missing_uuid(self):
        with self.assertRaises(EntryNotFound):
            self.update(self.first.uuid, "Line A", protocol="protocol/other")
        with self.assertRaises(EntryNotFound):
            self.update("missing", "Line A")
        self.assertEqual(self.first.num_availible_animals, 10)

    def add_animal(self, identifier, line, protocol="protocol", subprotocol="sub"):
        db.session.add(AnimalData({
            "id": identifier, "sex": "m", "line": line,
            "dob": "01.01.2025", "death_date": "", "user": "test",
            "protocol_pyrat": protocol, "protocol_escaped": protocol,
            "supplier": "", "subprotocol": subprotocol,
        }))

    def test_display_includes_used_lines_without_allowances_and_zero_usage(self):
        db.session.add_all([ALine("Line A"), ALine("Never used")])
        self.add_animal("1", "Imported line")
        self.add_animal("2", "Imported line")
        self.add_animal("3", "Line A")
        self.add_animal("4", "Elsewhere", subprotocol="other")
        self.add_animal("5", "Elsewhere", protocol="other")
        db.session.commit()
        rows, definitions = self.manager.get_protocol_data("allowed_animals", "protocol/sub")
        by_name = {row.name: row for row in rows}
        self.assertEqual({row.name: row.used for row in rows}, {
            "Imported line": 2, "Line A": 1, "Line B": 0,
        })
        self.assertEqual(by_name["Imported line"].uuid, "")
        self.assertIsNone(by_name["Imported line"].num_availible_animals)
        self.assertEqual({line.name for line in definitions}, {"Imported line", "Never used"})
        db.session.commit()
        self.assertEqual(PAllowedMice.query.count(), 2)
        self.assertEqual(ALine.query.count(), 2)
        # Saving the displayed missing line creates a real allowance.
        self.update("", "Imported line", "3")
        rows, definitions = self.manager.get_protocol_data("allowed_animals", "protocol/sub")
        configured = next(row for row in rows if row.name == "Imported line")
        self.assertTrue(configured.uuid)
        self.assertEqual(configured.used, 2)
        self.assertEqual(configured.num_availible_animals, 3)
        self.assertEqual({line.name for line in definitions}, {"Never used"})

    def test_unused_global_lines_can_be_configured_and_edited_per_subprotocol(self):
        db.session.add_all([ALine("Line A"), ALine("Never used")])
        db.session.commit()
        _, definitions = self.manager.get_protocol_data("allowed_animals", "protocol/other")
        self.assertEqual({line.name for line in definitions}, {"Line A", "Never used"})
        self.update("", "Never used", "10")
        row = PAllowedMice.query.filter_by(name="Never used").one()
        self.update(row.uuid, "Never used", "12")
        rows, definitions = self.manager.get_protocol_data("allowed_animals", "protocol/sub")
        self.assertEqual(next(row.used for row in rows if row.name == "Never used"), 0)
        self.assertNotIn("Never used", {line.name for line in definitions})
        self.assertEqual(AnimalData.query.count(), 0)

    def test_duplicate_creation_rejected(self):
        with self.assertRaises(DublicateEntry):
            self.update("", "Line A")

    def test_same_line_allowed_in_another_subprotocol_or_protocol(self):
        for protocol in ("protocol/other", "other/sub"):
            self.update("", "Line A", protocol=protocol)
        self.assertEqual(PAllowedMice.query.count(), 4)

    def test_database_rejects_duplicate_insert_and_update(self):
        db.session.add(PAllowedMice("protocol/sub", "Line A", 50))
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        self.second.name = "Line A"
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_blank_allowance_persists_as_null_on_create_and_edit(self):
        self.update("", "Unspecified", "")
        db.session.expire_all()
        row = PAllowedMice.query.filter_by(name="Unspecified").one()
        self.assertIsNone(row.num_availible_animals)
        for value in (None, "", "   "):
            self.update(self.first.uuid, "Line A", value)
            db.session.expire_all()
            self.assertIsNone(self.first.num_availible_animals)
        self.update(self.first.uuid, "Line A", "0")
        db.session.expire_all()
        self.assertEqual(self.first.num_availible_animals, 0)

    def test_invalid_allowances_rejected_on_create_and_edit(self):
        for value in ("-", "--", "abc", "1.5", "1e2", "-1", -1, 1.5, True):
            for uuid, name in (("", "New line"), (self.first.uuid, "Line A")):
                with self.subTest(value=value, uuid=uuid):
                    with self.assertRaises(InvalidTypeException):
                        self.update(uuid, name, value)
                    db.session.rollback()

    def test_database_rejects_invalid_allowances(self):
        for value in ("abc", "", "-", "--", -1, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(IntegrityError):
                    db.session.execute(db.text(
                        "UPDATE protocol_allowed_mice SET num_availible_animals = :value"
                    ), {"value": value})
                    db.session.commit()
                db.session.rollback()

    def test_display_distinguishes_unspecified_zero_and_numeric_limits(self):
        namespace = load_routes(self.app, {
            "handle_exception", "user_loader", "unauthorized_handler", "subprotocol",
        }, decorated=True)
        namespace["dmanager"] = self.manager
        db.session.delete(self.second)
        db.session.add_all([Protocol("Protocol", "protocol", "sub"),
                            User("test@example.org", "Test", False, "hash", b"salt")])
        db.session.commit()
        client = self.app.test_client()
        login_as(client, "test@example.org")
        for allowance, used, warning in ((None, 7, False), (0, 0, False),
                                         (0, 7, True), (10, 7, False), (10, 11, True)):
            with self.subTest(allowance=allowance, used=used):
                self.first.num_availible_animals = allowance
                AnimalData.query.delete()
                for identifier in range(used):
                    self.add_animal(str(identifier), "Line A")
                db.session.commit()
                response = client.get("/settings/protocols/protocol/sub/allowed_animals")
                self.assertEqual(response.status_code, 200, response.text)
                row, cell = AllowanceRows(response.text).rows[0]
                self.assertEqual("err" in row.get("class", "").split(), warning)
                self.assertEqual(cell["text"].strip(), "Not configured" if allowance is None else str(allowance))
                raw_value = "" if allowance is None else str(allowance)
                self.assertEqual(cell["data-value"], raw_value)


if __name__ == "__main__":
    unittest.main()
