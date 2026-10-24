"""Create empty subprotocols and independent copies through the real routes."""
import unittest
from unittest.mock import patch

from flask import Flask

from data_manager.dmanager import DManager
from data_manager.tables import (
    db, ALine, AProcedure, AnimalData, DEFINITION_TABLES, General, PAllowedMice,
    PGeneral, PMedication, PProcedure, PROTOCOL_TABLES, PVirus, PWatercontrol,
    Procedure, Protocol, User,
)
from exceptions.exceptions import (
    DublicateEntry, EntryNotFound, InvalidNameException, MissingEntryException,
)
from route_helpers import ROOT, load_routes


CONFIG_TABLES = (PGeneral, PWatercontrol, *PROTOCOL_TABLES.values())


class ProtocolCreationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / "src/templates"))
        self.app.config.update(
            SECRET_KEY="test-only", SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        )
        db.init_app(self.app)
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        namespace = load_routes(self.app, {
            "handle_exception", "user_loader", "unauthorized_handler",
            "protocol", "subprotocol", "add_subprotocal",
        }, decorated=True)
        self.manager = DManager()
        namespace["dmanager"] = self.manager
        self.source = Protocol("Source <protocol>", "source", "")
        self.target = Protocol("Target protocol", "target", "")
        db.session.add_all([self.source, self.target, Protocol("Unused", "unused", "")])
        self.source.add_subprotocol("A")
        self.source.add_subprotocol("Empty")
        self.target.add_subprotocol("Existing")
        general = PGeneral.query.filter_by(protocol="source/A").one()
        general.allowed_users = "Tester,Other"
        general.suffering = "Mittel"
        general.num_availible_animals = 42
        watercontrol = PWatercontrol.query.filter_by(protocol="source/A").one()
        watercontrol.allowed = False
        watercontrol.days_after_start = None
        watercontrol.duration = "10-12"
        surgery = PProcedure("source/A", "Surgery", "1-3", "2-4", True, False, 2, 1)
        medication = PMedication("source/A", "Medicine", "Kind", "Surgery", "0", "2", "1", False)
        # Preserve an amount that differs from the constructor's 30g calculation.
        medication.amount = "137.5"
        db.session.add_all([
            surgery,
            PProcedure("source/A", "Surgery", "30", "0", True, True, 0, None),
            PProcedure("source/A", "Optional", None, None, False, True, None, 0),
            PProcedure("source/A", "Sacrifice", "40", "1", False, False, 0, 0),
            medication,
            PMedication("source/A", "Medicine", "Kind", "Optional", "7", "2", "1", True),
            PVirus("source/A", "Required virus", "Surgery", "5", False),
            PVirus("source/A", "Optional virus", "Optional", "0", True),
            PAllowedMice("source/A", "Unspecified", None),
            PAllowedMice("source/A", "Zero", 0),
            PAllowedMice("source/A", "Limited", 12),
            ALine("Unspecified"),
            # The copy must preserve the stored surgery flag, independent of definitions.
            AProcedure("Surgery", 0, "1", False, 0, 0),
            AnimalData({
                "id": "animal", "sex": "m", "line": "Unspecified", "dob": "2025-01-01",
                "death_date": "", "user": "Tester", "protocol_pyrat": "Source",
                "protocol_escaped": "source", "subprotocol": "A", "supplier": "",
            }),
            General("animal", "source/A", False, "Mittel"),
            Procedure("animal", "Surgery", "2025-02-01", "2025-02-03", "Tester",
                      protocol_entry_uuid=surgery.uuid),
        ])
        user = User("tester@example.org", "Tester", True, "unused", b"unused")
        user.authenticated = True
        db.session.add(user)
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = user.email
            session["_fresh"] = True

    def rows(self, Table, protocol=None):
        query = Table.query
        if protocol is not None:
            query = query.filter_by(protocol=protocol)
        return [
            {column.name: getattr(row, column.name) for column in Table.__table__.columns}
            for row in query.all()
        ]

    def assert_no_destination(self, name="New"):
        self.assertNotIn(name, db.session.get(Protocol, "target").get_subprotocols())
        for Table in CONFIG_TABLES:
            self.assertEqual(self.rows(Table, f"target/{name}"), [])

    def test_empty_creation_keeps_defaults(self):
        result = self.manager.create_subprotocol("target", "New")
        db.session.commit()
        db.session.remove()
        self.assertEqual(result, "target/New")
        general = PGeneral.query.filter_by(protocol=result).one()
        watercontrol = PWatercontrol.query.filter_by(protocol=result).one()
        self.assertEqual((general.allowed_users, general.suffering, general.num_availible_animals),
                         ("", "Leicht", 10))
        self.assertEqual((watercontrol.allowed, watercontrol.days_after_start, watercontrol.duration),
                         (False, "0", "0"))
        for Table in PROTOCOL_TABLES.values():
            self.assertEqual(self.rows(Table, result), [])
        self.assertEqual(db.session.get(Protocol, "target").get_subprotocols(), ["Existing", "New"])

    def test_copy_preserves_all_settings_with_fresh_ids_in_same_or_other_parent(self):
        originals = {Table: self.rows(Table, "source/A") for Table in CONFIG_TABLES}
        unrelated_tables = (AnimalData, General, Procedure, *DEFINITION_TABLES.values())
        unrelated = {Table: self.rows(Table) for Table in unrelated_tables}
        all_ids = {row["uuid"] for rows in originals.values() for row in rows}
        for parent in ("source", "target"):
            with self.subTest(parent=parent):
                result = self.manager.create_subprotocol(parent, "New", template=("source", "A"))
                db.session.commit()
                db.session.remove()
                for Table, source_rows in originals.items():
                    copied = self.rows(Table, result)
                    self.assertEqual(len(copied), len(source_rows))
                    for row in copied:
                        self.assertEqual(row["protocol"], result)
                        self.assertNotIn(row["uuid"], all_ids)
                        all_ids.add(row["uuid"])
                    settings = lambda row: {k: v for k, v in row.items() if k not in ("uuid", "protocol")}
                    self.assertCountEqual([settings(row) for row in copied],
                                          [settings(row) for row in source_rows])
                    self.assertEqual(self.rows(Table, "source/A"), source_rows)
                for Table, rows in unrelated.items():
                    self.assertEqual(self.rows(Table), rows)

    def test_copy_of_empty_template_has_only_singleton_rows(self):
        self.manager.create_subprotocol("target", "New", template=("source", "Empty"))
        db.session.commit()
        self.assertEqual(PGeneral.query.filter_by(protocol="target/New").count(), 1)
        self.assertEqual(PWatercontrol.query.filter_by(protocol="target/New").count(), 1)
        for Table in PROTOCOL_TABLES.values():
            self.assertEqual(self.rows(Table, "target/New"), [])

    def test_edits_and_deletion_leave_the_other_copy_independent(self):
        self.manager.create_subprotocol("target", "New", template=("source", "A"))
        db.session.commit()
        copied = PVirus.query.filter_by(protocol="target/New", name="Required virus").one()
        self.manager.update_protocol_entry("viruses", "target/New", {
            "uuid": copied.uuid, "name": copied.name, "procedure": copied.procedure,
            "amount": "99",
        })
        db.session.commit()
        self.assertEqual(PVirus.query.filter_by(protocol="source/A", name=copied.name).one().amount, "5")
        copied_rows = {Table: self.rows(Table, "target/New") for Table in CONFIG_TABLES}
        self.manager.remove_subprotocol(db.session.get(Protocol, "source"), "source", "A")
        db.session.commit()
        db.session.remove()
        for Table, rows in copied_rows.items():
            self.assertEqual(self.rows(Table, "target/New"), rows)
        self.manager.remove_subprotocol(db.session.get(Protocol, "target"), "target", "New")
        db.session.commit()
        self.assert_no_destination()
        self.assertIn("Empty", db.session.get(Protocol, "source").get_subprotocols())

    def test_invalid_names_are_rejected_before_writing(self):
        for name in ("", " ", "New name", "New\tname", "New\nname", "New\u00a0name", "New/name", "New;name"):
            with self.subTest(name=name):
                with self.assertRaises(InvalidNameException):
                    self.manager.create_subprotocol("target", name, template=("source", "A"))
                self.assert_no_destination(name)

    def test_missing_parent_or_template_is_rejected(self):
        with self.assertRaises(EntryNotFound):
            self.manager.create_subprotocol("missing", "New")
        for template in (("missing", "A"), ("source", "missing"), ("source", "")):
            with self.subTest(template=template):
                with self.assertRaises(EntryNotFound):
                    self.manager.create_subprotocol("target", "New", template=template)
                self.assert_no_destination()

    def test_duplicate_name_never_overwrites_existing_settings(self):
        before = {Table: self.rows(Table, "source/A") for Table in CONFIG_TABLES}
        for template in (None, ("source", "A"), ("source", "Empty")):
            with self.subTest(template=template):
                with self.assertRaises(DublicateEntry):
                    self.manager.create_subprotocol("source", "A", template=template)
                for Table, rows in before.items():
                    self.assertEqual(self.rows(Table, "source/A"), rows)

    def test_missing_singletons_rejected_before_creating_destination(self):
        for Table in (PGeneral, PWatercontrol):
            with self.subTest(table=Table.__tablename__):
                db.session.delete(Table.query.filter_by(protocol="source/A").one())
                db.session.flush()
                with self.assertRaises(MissingEntryException):
                    self.manager.create_subprotocol("target", "New", template=("source", "A"))
                self.assert_no_destination()
                db.session.rollback()

    def test_creation_page_groups_templates_by_parent(self):
        response = self.client.get("/settings/protocols/target")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('action="/settings/protocols/target/add_protocol"', response.text)
        self.assertIn('<option value="">Start empty</option>', response.text)
        self.assertIn('<optgroup label="Source &lt;protocol&gt;">', response.text)
        self.assertRegex(response.text, r'<option value="source/A">\s*source/A\s*</option>')
        self.assertIn('<optgroup label="Target protocol">', response.text)
        self.assertRegex(response.text, r'<option value="target/Existing">\s*target/Existing\s*</option>')
        self.assertNotIn('<optgroup label="Unused">', response.text)

    def test_route_creates_and_redirects_to_general_with_or_without_template(self):
        for name, template in (("Empty", ""), ("Copied", "source/A")):
            with self.subTest(template=template):
                response = self.client.post("/settings/protocols/target/add_protocol", data={
                    "name": name, "template": template,
                })
                self.assertEqual(response.status_code, 302, response.text)
                self.assertEqual(response.location, f"/settings/protocols/target/{name}/general")
                page = self.client.get(response.location)
                self.assertEqual(page.status_code, 200, page.text)
                general = PGeneral.query.filter_by(protocol=f"target/{name}").one()
                self.assertEqual(general.allowed_users, "Tester,Other" if template else "")

    def test_route_accepts_existing_forms_without_a_template_field(self):
        response = self.client.post("/settings/protocols/target/add_protocol", data={"name": "New"})
        self.assertEqual(response.status_code, 302, response.text)
        self.assertEqual(PGeneral.query.filter_by(protocol="target/New").one().allowed_users, "")

    def test_route_rejects_malformed_or_missing_template(self):
        for template, status in (("source", 400), ("/A", 400), ("source/", 400),
                                 ("missing/A", 404), ("source/missing", 404)):
            with self.subTest(template=template):
                response = self.client.post("/settings/protocols/target/add_protocol", data={
                    "name": "New", "template": template,
                })
                self.assertEqual(response.status_code, status, response.text)
                self.assert_no_destination()

    def test_route_requires_login(self):
        client = self.app.test_client()
        response = client.post("/settings/protocols/target/add_protocol", data={
            "name": "New", "template": "source/A",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")
        self.assert_no_destination()

    def test_failed_copy_rolls_back_inserted_rows_and_subprotocol_registration(self):
        execute = db.session.execute
        inserted = []

        def fail_procedure_copy(statement, *args, **kwargs):
            if getattr(statement, "is_insert", False):
                if statement.table.name == PProcedure.__tablename__:
                    raise RuntimeError("Copy failed midway")
                inserted.append(statement.table.name)
            return execute(statement, *args, **kwargs)

        before = {Table: self.rows(Table, "source/A") for Table in CONFIG_TABLES}
        with patch.object(db.session, "execute", side_effect=fail_procedure_copy):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/settings/protocols/target/add_protocol", data={
                    "name": "New", "template": "source/A",
                })
        self.assertEqual(response.status_code, 500)
        self.assertIn(PGeneral.__tablename__, inserted)
        self.assertIn(PAllowedMice.__tablename__, inserted)
        db.session.remove()
        self.assert_no_destination()
        for Table, rows in before.items():
            self.assertEqual(self.rows(Table, "source/A"), rows)


if __name__ == "__main__":
    unittest.main()
