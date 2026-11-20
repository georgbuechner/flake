"""Paw-control defaults, membership management and the admin UI."""
from html.parser import HTMLParser
import unittest

from flask import Flask

from data_manager.dmanager import DManager
from data_manager.tables import db, User, table_to_json
from route_helpers import ROOT, load_routes


class InputParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))


class PawControlTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / "src/templates"))
        self.app.config.update(SECRET_KEY="test-only", SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        db.init_app(self.app)
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        namespace = load_routes(self.app, decorated=True)
        namespace["dmanager"] = DManager()
        self.admin = User("admin@example.org", "Admin", True, "hash", b"salt")
        self.user = User("user@example.org", "User", False, "hash", b"salt")
        db.session.add_all([self.admin, self.user])
        db.session.commit()
        self.client = self.app.test_client()
        self.ajax = {"X-Requested-With": "XMLHttpRequest"}
        self.login(self.admin)

    def login(self, user):
        with self.client.session_transaction() as session:
            session["_user_id"] = user.email
            session["_fresh"] = True

    def test_new_users_default_to_false_before_and_after_persistence(self):
        user = User("new@example.org", "New", False, "hash", b"salt")
        self.assertIs(user.paw_control, False)
        db.session.add(user)
        db.session.commit()
        db.session.remove()
        self.assertIs(db.session.get(User, "new@example.org").paw_control, False)
        self.assertIs(db.session.get(User, "admin@example.org").paw_control, False)

    def test_serialization_preserves_membership_and_accepts_legacy_users(self):
        db.session.refresh(self.user)
        self.user.paw_control = True
        payload = table_to_json(self.user)
        self.assertIs(User.from_json(payload).paw_control, True)
        del payload["paw_control"]
        self.assertIs(User.from_json(payload).paw_control, False)

    def test_admin_can_enable_and_disable_membership_without_changing_admin_status(self):
        for admin in (False, True):
            self.user.admin = admin
            db.session.commit()
            for enabled in (True, False):
                with self.subTest(admin=admin, enabled=enabled):
                    response = self.client.post(
                        "/account/user@example.org/set_paw_control",
                        query_string={"paw_control": "True"} if enabled else {}, headers=self.ajax,
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    db.session.expire_all()
                    user = db.session.get(User, "user@example.org")
                    self.assertIs(user.paw_control, enabled)
                    self.assertIs(user.admin, admin)
                    self.user = user

    def test_admin_toggle_still_changes_only_admin_status(self):
        self.user.paw_control = True
        db.session.commit()
        for enabled in (True, False):
            response = self.client.post("/account/user@example.org/set_admin",
                                        query_string={"admin": "True"} if enabled else {}, headers=self.ajax)
            self.assertEqual(response.status_code, 302)
            db.session.expire_all()
            user = db.session.get(User, "user@example.org")
            self.assertIs(user.admin, enabled)
            self.assertIs(user.paw_control, True)

    def test_non_admins_including_members_cannot_change_membership(self):
        self.login(self.user)
        for member in (False, True):
            db.session.get(User, "user@example.org").paw_control = member
            db.session.commit()
            for target in ("user@example.org", "admin@example.org"):
                with self.subTest(member=member, target=target):
                    response = self.client.post(f"/account/{target}/set_paw_control?paw_control=True",
                                                headers=self.ajax)
                    self.assertEqual(response.status_code, 403)
                    db.session.expire_all()
                    self.assertIs(db.session.get(User, "user@example.org").paw_control, member)
                    self.assertIs(db.session.get(User, "admin@example.org").paw_control, False)

    def test_anonymous_requests_cannot_change_membership(self):
        response = self.app.test_client().post("/account/user@example.org/set_paw_control?paw_control=True",
                                               headers=self.ajax)
        self.assertEqual(response.status_code, 401)
        self.assertIs(db.session.get(User, "user@example.org").paw_control, False)

    def test_unknown_user_returns_404(self):
        response = self.client.post("/account/missing@example.org/set_paw_control?paw_control=True",
                                    headers=self.ajax)
        self.assertEqual(response.status_code, 404)

    def test_management_page_renders_valid_checked_and_unchecked_controls(self):
        self.user.paw_control = True
        db.session.commit()
        response = self.client.get("/settings/user-management")
        self.assertEqual(response.status_code, 200, response.text)
        parser = InputParser()
        parser.feed(response.text)
        controls = [item for item in parser.inputs if item.get("name") in ("admin", "paw_control")]
        self.assertEqual(len(controls), 4)
        self.assertEqual(len({item["id"] for item in controls}), 4)
        for control in controls:
            is_admin = control["name"] == "admin"
            handler = "SetAdmin" if is_admin else "SetPawControl"
            self.assertTrue(control["onchange"].startswith(handler + "("))
            checked_user = "admin@example.org" if is_admin else "user@example.org"
            expected = checked_user in control["onchange"]
            self.assertEqual("checked" in control, expected)


if __name__ == "__main__":
    unittest.main()
