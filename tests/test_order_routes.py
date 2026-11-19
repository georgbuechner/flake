"""Native order pages, form redirects, privacy and transactional review decisions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from flask import Flask, g, template_rendered
from werkzeug.datastructures import MultiDict

from data_manager import orders as order_manager
from data_manager.tables import (
    AnimalData, AnimalOrder, AnimalOrderByData, AnimalOrderById, PAllowedMice,
    PGeneral, Protocol, User, db,
)
from route_helpers import ROOT, load_routes


class OrderRouteFixture:
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / "src/templates"))
        self.app.config.update(
            SECRET_KEY="test-only",
            SQLALCHEMY_DATABASE_URI=getattr(self, "database_url", "sqlite:///:memory:"),
        )
        db.init_app(self.app)
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        db.create_all()
        self.ns = load_routes(self.app, decorated=True)

        @self.app.before_request
        def clear_cached_test_user():
            # Database assertions keep an app context open across requests.
            # Production requests each get a fresh g and reload their user.
            g.pop("_login_user", None)

        clock = patch("data_manager.orders.today", return_value=datetime(2026, 11, 19))
        clock.start()
        self.addCleanup(clock.stop)
        self.owner_email = "requester@example.org"
        self.other_email = "other@example.org"
        self.admin_email = "admin@example.org"
        self.reviewer_email = "reviewer@example.org"
        self.allowance = PAllowedMice("protocol/A", "Line A", 5)
        db.session.add_all([
            User(self.owner_email, "Requester", False, "hash", b"salt"),
            User(self.other_email, "Other", False, "hash", b"salt"),
            User(self.admin_email, "Admin", True, "hash", b"salt"),
            User(self.reviewer_email, "Reviewer", False, "hash", b"salt", paw_control=True),
            Protocol("Protocol", "protocol", "A;Hidden;Empty"),
            PGeneral("protocol/A", 0, "Requester, Other", "Leicht"),
            PGeneral("protocol/Hidden", 0, "Other", "Leicht"),
            PGeneral("protocol/Empty", 0, "Requester", "Leicht"),
            self.allowance, PAllowedMice("protocol/A", "Unspecified", None),
            PAllowedMice("protocol/A", "Zero", 0),
        ])
        self.add_animal("001", user="Other", death_date="2025-01-01")
        self.add_animal("002")
        self.data = {
            "order_type": "by_data", "licence": "protocol/A", "line": "Line A",
            "date": "2026-11-22", "sex": "female", "age": "8", "amount": "2",
        }
        self.ids = {
            "order_type": "by_id", "licence": "protocol/A", "line": "Line A",
            "date": "2026-11-22", "ids": ["NEW-1", "NEW-2"],
        }
        own = AnimalOrderByData(
            licence="protocol/A", line="Line A", date=date(2026, 11, 22),
            user=self.owner_email, sex="female", age=8, amount=2,
        )
        own.created_at = datetime(2026, 11, 19, 10)
        rejected = AnimalOrderById(
            licence="protocol/A", line="Line A", date=date(2026, 11, 22),
            user=self.owner_email, ids=["OLD-1"],
        )
        rejected.created_at = datetime(2026, 11, 18, 10)
        rejected.status = "rejected"
        other = AnimalOrderById(
            licence="protocol/A", line="Line A", date=date(2026, 11, 22),
            user=self.other_email, ids=["OTHER-1"],
        )
        other.created_at = datetime(2026, 11, 20, 10)
        db.session.add_all([own, rejected, other])
        db.session.commit()
        self.own_uuid, self.rejected_uuid, self.other_uuid = own.uuid, rejected.uuid, other.uuid
        self.allowance_uuid = self.allowance.uuid
        self.client = self.app.test_client()
        self.client.environ_base["HTTP_ACCEPT"] = "text/html"
        self.login(self.owner_email)

    def login(self, email, client=None):
        with (client or self.client).session_transaction() as session:
            session["_user_id"] = email
            session["_fresh"] = True

    def add_animal(self, identifier, *, user="Requester", death_date=""):
        db.session.add(AnimalData({
            "id": identifier, "sex": "m", "line": "Line A", "dob": "2020-01-01",
            "death_date": death_date, "user": user, "protocol_pyrat": "Protocol",
            "protocol_escaped": "protocol", "subprotocol": "A", "supplier": "",
        }))

    def stored_status(self, order_uuid):
        db.session.remove()
        return db.session.get(AnimalOrder, order_uuid).status

    def review(self, order_uuid, status, **kwargs):
        return self.client.post(f"/orders/{order_uuid}/status", data={"status": status}, **kwargs)


@contextmanager
def captured_templates(app):
    rendered = []

    def record(sender, template, context, **extra):
        rendered.append((template.name, context))

    template_rendered.connect(record, app)
    try:
        yield rendered
    finally:
        template_rendered.disconnect(record, app)


class OrderPageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = []
        self.order_rows = []
        self.inputs = []
        self.textareas = {}
        self.selects = {}
        self.current_form = None
        self.current_textarea = None
        self.current_select = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current_form = {**attrs, "inputs": []}
            self.forms.append(self.current_form)
        elif tag == "input":
            self.inputs.append(attrs)
            if self.current_form is not None:
                self.current_form["inputs"].append(attrs)
        elif tag == "textarea":
            self.current_textarea = attrs.get("id")
            self.textareas[self.current_textarea] = ""
        elif tag == "select":
            self.current_select = attrs.get("id")
            self.selects[self.current_select] = []
        elif tag == "option" and self.current_select is not None:
            self.selects[self.current_select].append(attrs)
        elif tag == "tr" and attrs.get("id", "").startswith("order-"):
            self.order_rows.append(attrs["id"][len("order-"):])

    def handle_endtag(self, tag):
        if tag == "form":
            self.current_form = None
        elif tag == "textarea":
            self.current_textarea = None
        elif tag == "select":
            self.current_select = None

    def handle_data(self, data):
        if self.current_textarea is not None:
            self.textareas[self.current_textarea] += data

    def form(self, identifier):
        return next(form for form in self.forms if form.get("id") == identifier)

    def hidden_values(self, form):
        return {field["name"]: field.get("value", "") for field in form["inputs"]
                if field.get("type") == "hidden"}


class OrderRouteTests(OrderRouteFixture, unittest.TestCase):
    def page(self, **query):
        with captured_templates(self.app) as rendered:
            response = self.client.get("/orders", query_string=query)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rendered[-1][0], "orders.html")
        return response, rendered[-1][1], OrderPageParser(response.text)

    def test_initial_page_requires_a_licence_selection_before_showing_the_order_form(self):
        response, context, page = self.page()
        self.assertEqual(context["selected_licence"], "")
        self.assertEqual(context["lines"], [])
        self.assertFalse(context["can_submit"])
        self.assertFalse(any(form.get("id") == "new-order" for form in page.forms))
        self.assertEqual(
            [option["value"] for option in page.selects["licence"] if "selected" in option],
            [""],
        )
        self.assertIn("Select a licence", response.text)
        self.assertEqual(page.order_rows, [self.own_uuid, self.rejected_uuid])

    def test_page_passes_order_objects_to_jinja_with_scoped_licences_and_capacity(self):
        response, context, page = self.page(licence="protocol/A")
        self.assertEqual(response.mimetype, "text/html")
        self.assertFalse(response.is_json)
        self.assertTrue(all(isinstance(order, AnimalOrder) for order in context["orders"]))
        self.assertEqual(page.order_rows, [self.own_uuid, self.rejected_uuid])
        self.assertEqual([choice["licence"] for choice in context["licences"]], ["protocol/A", "protocol/Empty"])
        self.assertEqual(context["selected_licence"], "protocol/A")
        self.assertEqual(
            [option["value"] for option in page.selects["licence"] if "selected" in option],
            ["protocol/A"],
        )
        self.assertEqual(context["lines"], [
            {"line": "Line A", "allowance": 5, "used": 2, "remaining": 3},
            {"line": "Unspecified", "allowance": None, "used": 0, "remaining": None},
            {"line": "Zero", "allowance": 0, "used": 0, "remaining": 0},
        ])
        self.assertIn("3 remaining (2 assigned / 5 allowed)", response.text)
        self.assertNotIn("protocol/Hidden", response.text)
        self.assertFalse(context["can_review"])
        self.assertEqual(context["users"], [{"email": self.owner_email, "name": "Requester"}])
        unavailable = {option["value"] for option in page.selects["line"] if "disabled" in option}
        self.assertEqual(unavailable, {"Unspecified", "Zero"})
        self.assertEqual(next(field for field in page.inputs if field.get("id") == "date")["min"], "2026-11-22")

    def test_selection_and_filters_are_get_forms_and_change_the_rendered_input_mode(self):
        response, context, page = self.page(licence="protocol/A", order_type="by_id")
        self.assertEqual(page.form("order-selection")["method"].upper(), "GET")
        self.assertEqual(page.form("order-filters")["method"].upper(), "GET")
        self.assertEqual(page.form("order-selection")["action"], "/orders")
        self.assertIn("ids", page.textareas)
        self.assertFalse(any(field.get("name") in ("age", "amount") for field in page.inputs))
        self.assertIn("Order by ID", response.text)
        response, context, page = self.page(licence="protocol/Empty", order_type="by_data")
        self.assertFalse(context["can_submit"])
        self.assertIn("No lines are configured", response.text)
        for licence, status in (("protocol/Hidden", 403), ("missing/A", 404)):
            self.assertEqual(self.client.get("/orders", query_string={"licence": licence}).status_code, status)
        self.assertEqual(self.client.get("/orders?order_type=other").status_code, 400)

    def test_details_render_the_python_object_and_hide_other_users_orders(self):
        with captured_templates(self.app) as rendered:
            response = self.client.get(f"/orders/{self.own_uuid}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rendered[-1][0], "order.html")
        self.assertIsInstance(rendered[-1][1]["order"], AnimalOrderByData)
        self.assertEqual(OrderPageParser(response.text).order_rows, [self.own_uuid])
        self.assertIn("22.11.2026", response.text)
        self.assertIn("2 × female, 8 weeks", response.text)
        self.assertNotIn("Approve", response.text)
        for order_uuid in (self.other_uuid, "missing"):
            self.assertEqual(self.client.get(f"/orders/{order_uuid}").status_code, 404)

    def test_filters_cannot_expand_regular_user_visibility(self):
        response, context, page = self.page(user=self.owner_email, status="rejected")
        self.assertEqual(page.order_rows, [self.rejected_uuid])
        self.assertEqual(context["filters"], {"user": self.owner_email, "status": "rejected"})
        self.assertEqual(self.client.get("/orders", query_string={"user": self.other_email}).status_code, 403)
        self.assertEqual(self.client.get("/orders?status=ordered").status_code, 400)

    def test_paw_control_can_filter_all_orders_and_retains_requester_choices(self):
        self.login(self.reviewer_email)
        response, context, page = self.page()
        self.assertTrue(context["can_review"])
        self.assertEqual(page.order_rows, [self.other_uuid, self.own_uuid, self.rejected_uuid])
        users = [{"email": self.other_email, "name": "Other"},
                 {"email": self.owner_email, "name": "Requester"}]
        self.assertEqual(context["users"], users)
        self.assertIn("Approve", response.text)
        self.assertEqual(len([form for form in page.forms if form["action"].endswith("/status")]), 2)
        response, context, page = self.page(user=self.other_email, status="pending")
        self.assertEqual(page.order_rows, [self.other_uuid])
        self.assertEqual(context["users"], users)
        self.assertIn("No licences are available", response.text)
        response, context, page = self.page(user="missing@example.org")
        self.assertEqual(page.order_rows, [])
        self.assertIn("No orders match", response.text)

    def test_admin_status_does_not_grant_cross_user_visibility_or_review_permissions(self):
        for email in (self.owner_email, self.admin_email):
            self.login(email)
            response, context, page = self.page()
            self.assertFalse(context["can_review"])
            self.assertNotIn(self.other_uuid, page.order_rows)
            self.assertFalse(any(form["action"].endswith("/status") for form in page.forms))
            self.assertEqual(self.client.get(f"/orders/{self.other_uuid}").status_code, 404)
            self.assertEqual(self.review(self.other_uuid, "approved").status_code, 403)
            self.assertEqual(self.review(self.own_uuid, "rejected").status_code, 403)
        self.assertEqual(self.stored_status(self.other_uuid), "pending")

    def test_native_submission_redirects_before_rendering_and_refresh_does_not_duplicate(self):
        response, context, page = self.page(licence="protocol/A")
        form = page.form("new-order")
        self.assertEqual(form["method"].upper(), "POST")
        self.assertNotIn("data-ajax-submit", form)
        before = AnimalOrder.query.count()
        response = self.client.post(form["action"], data={
            **page.hidden_values(form), **self.data, "comment": "Requested animals",
            "user": self.other_email, "status": "approved", "uuid": "forged", "created_at": "2000-01-01",
        })
        self.assertEqual(response.status_code, 303, response.text)
        location = response.headers["Location"]
        self.assertTrue(location.startswith("/orders?"))
        db.session.remove()
        self.assertEqual(AnimalOrder.query.count(), before + 1)
        order = AnimalOrder.query.filter(AnimalOrder.uuid.notin_(
            [self.own_uuid, self.rejected_uuid, self.other_uuid])).one()
        self.assertIsInstance(order, AnimalOrderByData)
        self.assertEqual((order.user, order.status, order.amount), (self.owner_email, "pending", 2))
        self.assertNotEqual(order.uuid, "forged")
        identifier = order.uuid
        response = self.client.get(location)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Order submitted.", response.text)
        self.assertIn(identifier, OrderPageParser(response.text).order_rows)
        self.client.get(location)
        self.assertEqual(AnimalOrder.query.count(), before + 1)
        self.assertEqual(AnimalData.query.count(), 2)

    def test_id_orders_work_from_the_reloaded_form_and_repeated_native_fields(self):
        response, context, page = self.page(licence="protocol/A", order_type="by_id")
        form = page.form("new-order")
        submissions = (
            {**page.hidden_values(form), "line": "Line A", "date": "2026-11-22", "ids": "NEW-1,\nNEW-2"},
            MultiDict([(key, value) for key, value in self.ids.items() if key != "ids"] +
                      [("ids", "NEW-1"), ("ids", "NEW-2")]),
        )
        for data in submissions:
            before = {order.uuid for order in AnimalOrder.query.all()}
            response = self.client.post(form["action"], data=data)
            self.assertEqual(response.status_code, 303, response.text)
            db.session.remove()
            order = AnimalOrder.query.filter(AnimalOrder.uuid.notin_(before)).one()
            self.assertIsInstance(order, AnimalOrderById)
            self.assertEqual(order.ids, ["NEW-1", "NEW-2"])
            response = self.client.get(response.headers["Location"])
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIn("IDs: NEW-1, NEW-2", response.text)

    def test_validation_errors_rerender_the_form_with_values_and_no_writes(self):
        before = AnimalOrder.query.count()
        for changes, status in (
            ({"amount": "4"}, 409), ({"line": "Zero"}, 409), ({"line": "Unspecified"}, 409),
            ({"line": "Missing"}, 404), ({"licence": "protocol/Hidden"}, 403),
            ({"date": "2026-11-21"}, 400), ({"amount": "1.5"}, 400), ({"order_type": "other"}, 400),
        ):
            with self.subTest(changes=changes), captured_templates(self.app) as rendered:
                response = self.client.post("/orders", data={**self.data, **changes, "comment": "Keep this comment"})
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(response.mimetype, "text/html")
                self.assertEqual(rendered[-1][0], "orders.html")
                self.assertTrue(rendered[-1][1]["error"])
                self.assertEqual(OrderPageParser(response.text).textareas.get("comment"), "Keep this comment" if changes.get("licence") != "protocol/Hidden" else None)
                db.session.remove()
                self.assertEqual(AnimalOrder.query.count(), before)
        response = self.client.post("/orders", data={**self.ids, "ids": "NEW-1, NEW-1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(OrderPageParser(response.text).textareas["ids"], "NEW-1, NEW-1")
        self.assertEqual(AnimalOrder.query.count(), before)

    def test_jinja_escapes_comments_ids_and_errors_instead_of_injecting_html(self):
        comment = '<script>alert("comment")</script>'
        db.session.get(AnimalOrder, self.own_uuid).comment = comment
        db.session.get(AnimalOrder, self.rejected_uuid).ids = ["<img src=x onerror=alert(1)>"]
        db.session.commit()
        response = self.client.get("/orders")
        self.assertNotIn(comment, response.text)
        self.assertNotIn("<img src=x", response.text)
        self.assertIn("&lt;script&gt;", response.text)
        self.assertIn("&lt;img", response.text)
        response = self.client.post("/orders", data={**self.data, "age": "<svg/onload=alert(1)>"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("<svg/onload=alert(1)>", response.text)
        self.assertIn("&lt;svg", response.text)

    def test_order_routes_require_login_and_keep_native_redirects(self):
        anonymous = self.app.test_client()
        for method, path in (
            ("GET", "/orders"), ("POST", "/orders"),
            ("GET", f"/orders/{self.own_uuid}"), ("POST", f"/orders/{self.own_uuid}/status"),
        ):
            with self.subTest(method=method, path=path):
                response = anonymous.open(path, method=method)
                self.assertEqual(response.status_code, 302, response.text)
                self.assertEqual(response.headers["Location"], "/login")
        response = anonymous.post("/orders", headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/api/orders").status_code, 404)
        self.assertEqual(self.client.post("/orders", json=self.data).status_code, 400)
        self.assertEqual(self.client.get(f"/orders/{self.own_uuid}/status").status_code, 405)

    def test_paw_control_review_posts_redirect_and_preserve_filters(self):
        self.login(self.reviewer_email)
        response, context, page = self.page(user=self.other_email, status="pending")
        form = next(form for form in page.forms if form["action"].endswith("/status"))
        response = self.client.post(form["action"], data={**page.hidden_values(form), "status": "approved"})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.stored_status(self.other_uuid), "approved")
        with captured_templates(self.app) as rendered:
            response = self.client.get(response.headers["Location"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(rendered[-1][1]["filters"], {"user": self.other_email, "status": "pending"})
        self.assertIn("Order approved.", response.text)
        self.assertEqual(OrderPageParser(response.text).order_rows, [])
        self.assertEqual(AnimalData.query.count(), 2)

    def test_review_from_details_redirects_to_the_updated_detail_page(self):
        self.login(self.reviewer_email)
        response = self.client.get(f"/orders/{self.own_uuid}")
        page = OrderPageParser(response.text)
        form = next(form for form in page.forms if form["action"].endswith("/status"))
        response = self.client.post(form["action"], data={**page.hidden_values(form), "status": "rejected"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], f"/orders/{self.own_uuid}")
        response = self.client.get(response.headers["Location"])
        self.assertIn("Order rejected.", response.text)
        self.assertNotIn("Approve", response.text)
        self.assertEqual(self.stored_status(self.own_uuid), "rejected")

    def test_review_rejects_invalid_decisions_and_prevents_reversals(self):
        self.login(self.reviewer_email)
        for status in (None, "", "pending", "ordered", "other"):
            with self.subTest(status=status):
                self.assertEqual(self.review(self.own_uuid, status).status_code, 400)
                self.assertEqual(self.stored_status(self.own_uuid), "pending")
        self.assertEqual(self.review("missing", "approved").status_code, 404)
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 303)
        for status in ("approved", "rejected"):
            self.assertEqual(self.review(self.own_uuid, status).status_code, 409)
            self.assertEqual(self.stored_status(self.own_uuid), "approved")
        self.assertEqual(self.review(self.rejected_uuid, "approved").status_code, 409)

    def test_approval_rechecks_capacity_but_not_submission_lead_time(self):
        self.login(self.reviewer_email)
        self.add_animal("003")
        self.add_animal("004")
        db.session.commit()
        response = self.review(self.own_uuid, "approved")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.stored_status(self.own_uuid), "pending")
        db.session.get(PAllowedMice, self.allowance_uuid).num_availible_animals = 6
        db.session.commit()
        with patch("data_manager.orders.today", return_value=datetime(2026, 11, 22)):
            response = self.review(self.own_uuid, "approved")
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.stored_status(self.own_uuid), "approved")

    def test_removed_licences_can_be_rejected_and_historical_orders_stay_visible(self):
        self.login(self.reviewer_email)
        db.session.delete(db.session.get(Protocol, "protocol"))
        db.session.commit()
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 404)
        self.assertEqual(self.stored_status(self.own_uuid), "pending")
        self.assertEqual(self.review(self.own_uuid, "rejected").status_code, 303)
        self.login(self.owner_email)
        response, context, page = self.page()
        self.assertEqual(page.order_rows, [self.own_uuid, self.rejected_uuid])
        self.assertEqual(context["licences"], [])

    def test_missing_and_unconfigured_allowances_block_approval(self):
        self.login(self.reviewer_email)
        db.session.get(PAllowedMice, self.allowance_uuid).num_availible_animals = None
        db.session.commit()
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 409)
        self.assertEqual(self.stored_status(self.own_uuid), "pending")
        db.session.delete(PAllowedMice.query.filter_by(protocol="protocol/A", name="Line A").one())
        db.session.commit()
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 404)
        self.assertEqual(self.review(self.own_uuid, "rejected").status_code, 303)

    def test_deleted_accounts_use_stored_emails_and_membership_revocation_takes_effect(self):
        db.session.delete(db.session.get(User, self.other_email))
        db.session.commit()
        self.login(self.reviewer_email)
        response, context, page = self.page()
        self.assertIn({"email": self.other_email, "name": self.other_email}, context["users"])
        self.assertEqual(len(page.order_rows), 3)
        db.session.get(User, self.reviewer_email).paw_control = False
        db.session.commit()
        db.session.remove()
        response, context, page = self.page()
        self.assertFalse(context["can_review"])
        self.assertEqual(page.order_rows, [])
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 403)

    def test_commit_failures_roll_back_creation_and_review(self):
        before = AnimalOrder.query.count()
        with patch.object(db.session, "commit", side_effect=RuntimeError("private database details")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/orders", data=self.data)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "text/html")
        self.assertNotIn("private database details", response.text)
        db.session.remove()
        self.assertEqual(AnimalOrder.query.count(), before)
        self.login(self.reviewer_email)
        with patch.object(db.session, "commit", side_effect=RuntimeError("private database details")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.review(self.own_uuid, "approved")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.stored_status(self.own_uuid), "pending")


class OrderReviewConcurrencyTests(OrderRouteFixture, unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="flake-order-review-")
        self.addCleanup(directory.cleanup)
        self.database_url = "sqlite:///" + str(Path(directory.name) / "test.db")
        super().setUp()

    def test_two_reviewers_cannot_replace_each_others_decision(self):
        second_email = "second-reviewer@example.org"
        db.session.add(User(second_email, "Second reviewer", False, "hash", b"salt", paw_control=True))
        db.session.commit()
        barrier = Barrier(2, timeout=5)
        original = order_manager.get_order

        def synchronized_get_order(user, order_uuid):
            order = original(user, order_uuid)
            barrier.wait()
            return order

        def review(email, status):
            client = self.app.test_client()
            client.environ_base["HTTP_ACCEPT"] = "text/html"
            self.login(email, client)
            response = client.post(f"/orders/{self.own_uuid}/status", data={"status": status})
            return status, response.status_code

        with patch("data_manager.orders.get_order", side_effect=synchronized_get_order):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(review, self.reviewer_email, "approved"),
                           executor.submit(review, second_email, "rejected")]
                results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual([code for status, code in results], [303, 409])
        winner = next(status for status, code in results if code == 303)
        self.assertEqual(self.stored_status(self.own_uuid), winner)


if __name__ == "__main__":
    unittest.main()
