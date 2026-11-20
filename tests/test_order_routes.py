"""Native order pages, form redirects, privacy and transactional review decisions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from data_manager import orders as order_manager
from data_manager.tables import (
    AnimalData, AnimalOrder, AnimalOrderByData, AnimalOrderById, PAllowedMice,
    PGeneral, Protocol, User, db,
)
from helpers import database_app, login_as
from route_helpers import load_routes


class OrderRouteFixture:
    def setUp(self):
        self.app = database_app(self, database_url=getattr(self, "database_url", "sqlite:///:memory:"))
        self.ns = load_routes(self.app, decorated=True)

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
        login_as(client or self.client, email)

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
        response = self.client.get("/orders", query_string=query)
        self.assertEqual(response.status_code, 200, response.text)
        return response, OrderPageParser(response.text)

    def test_initial_page_waits_for_an_explicit_licence_selection(self):
        response, page = self.page()
        self.assertEqual(page.order_rows, [self.own_uuid, self.rejected_uuid])
        self.assertFalse(any(form.get("id") == "new-order" for form in page.forms))
        self.assertEqual([option["value"] for option in page.selects["licence"] if "selected" in option], [""])
        for identifier in ("order-selection", "order-filters"):
            self.assertEqual(page.form(identifier)["method"].upper(), "GET")

    def test_licence_and_mode_selection_render_the_native_form_and_capacity(self):
        for mode in ("by_data", "by_id"):
            with self.subTest(mode=mode):
                response, page = self.page(licence="protocol/A", order_type=mode)
                self.assertEqual([option["value"] for option in page.selects["licence"] if "selected" in option], ["protocol/A"])
                self.assertNotIn("protocol/Hidden", response.text)
                self.assertIn("3 remaining (2 assigned / 5 allowed)", response.text)
                self.assertEqual({option["value"] for option in page.selects["line"] if "disabled" in option}, {"Unspecified", "Zero"})
                self.assertEqual("ids" in page.textareas, mode == "by_id")
                self.assertEqual(any(field.get("name") == "amount" for field in page.inputs), mode == "by_data")
                self.assertEqual(next(field for field in page.inputs if field.get("id") == "date")["min"], "2026-11-22")
        response, page = self.page(licence="protocol/Empty")
        self.assertIn("No lines are configured", response.text)
        self.assertIn("<fieldset disabled>", response.text)
        for query, status in (({"licence": "protocol/Hidden"}, 403),
                              ({"licence": "missing/A"}, 404), ({"order_type": "other"}, 400)):
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/orders", query_string=query).status_code, status)

    def test_regular_users_and_admins_cannot_view_or_review_other_users_orders(self):
        for email in (self.owner_email, self.admin_email):
            with self.subTest(user=email):
                self.login(email)
                response, page = self.page()
                expected = [self.own_uuid, self.rejected_uuid] if email == self.owner_email else []
                self.assertEqual(page.order_rows, expected)
                self.assertFalse(any(form["action"].endswith("/status") for form in page.forms))
                self.assertEqual(self.client.get(f"/orders/{self.other_uuid}").status_code, 404)
                self.assertEqual(self.client.get("/orders", query_string={"user": self.other_email}).status_code, 403)
                self.assertEqual(self.review(self.other_uuid, "approved").status_code, 403)
                self.assertEqual(self.review(self.own_uuid, "rejected").status_code, 403)
        self.assertEqual(self.stored_status(self.other_uuid), "pending")
        self.login(self.owner_email)
        response, page = self.page(status="rejected")
        self.assertEqual(page.order_rows, [self.rejected_uuid])
        response = self.client.get(f"/orders/{self.own_uuid}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OrderPageParser(response.text).order_rows, [self.own_uuid])
        self.assertIn("2 × female, 8 weeks", response.text)
        self.assertIn("22.11.2026", response.text)
        self.assertEqual(self.client.get("/orders/missing").status_code, 404)

    def test_paw_control_sees_all_orders_and_filters_without_losing_requester_choices(self):
        self.login(self.reviewer_email)
        response, page = self.page()
        self.assertEqual(page.order_rows, [self.other_uuid, self.own_uuid, self.rejected_uuid])
        self.assertEqual(len([form for form in page.forms if form["action"].endswith("/status")]), 2)
        response, page = self.page(user=self.other_email, status="pending")
        self.assertEqual(page.order_rows, [self.other_uuid])
        self.assertEqual({option["value"] for option in page.selects["filter-user"]},
                         {"", self.owner_email, self.other_email})
        self.assertIn("No licences are available", response.text)
        response, page = self.page(user="missing@example.org")
        self.assertEqual(page.order_rows, [])
        self.assertEqual(self.client.get("/orders?status=ordered").status_code, 400)

    def test_native_submission_derives_metadata_and_refresh_does_not_duplicate(self):
        response, page = self.page(licence="protocol/A")
        form = page.form("new-order")
        self.assertEqual(form["method"].upper(), "POST")
        self.assertNotIn("data-ajax-submit", form)
        before = {order.uuid for order in AnimalOrder.query.all()}
        response = self.client.post(form["action"], data={
            **page.hidden_values(form), **self.data, "comment": "Requested animals",
            "user": self.other_email, "status": "approved", "uuid": "forged", "created_at": "2000-01-01",
        })
        self.assertEqual(response.status_code, 303, response.text)
        location = response.headers["Location"]
        db.session.remove()
        order = AnimalOrder.query.filter(AnimalOrder.uuid.notin_(before)).one()
        self.assertEqual((order.user, order.status, order.amount), (self.owner_email, "pending", 2))
        self.assertNotEqual(order.uuid, "forged")
        self.assertNotEqual(order.created_at.year, 2000)
        identifier = order.uuid
        response = self.client.get(location)
        self.assertIn("Order submitted.", response.text)
        self.assertIn(identifier, OrderPageParser(response.text).order_rows)
        self.client.get(location)
        self.assertEqual(AnimalOrder.query.count(), len(before) + 1)
        self.assertEqual(AnimalData.query.count(), 2)

    def test_id_orders_accept_textarea_and_repeated_native_fields(self):
        response, page = self.page(licence="protocol/A", order_type="by_id")
        form = page.form("new-order")
        submissions = (
            {**page.hidden_values(form), "line": "Line A", "date": "2026-11-22", "ids": "NEW-1,\nNEW-2"},
            MultiDict([(key, value) for key, value in self.ids.items() if key != "ids"] +
                      [("ids", "NEW-1"), ("ids", "NEW-2")]),
        )
        for data in submissions:
            with self.subTest(fields=type(data).__name__):
                before = {order.uuid for order in AnimalOrder.query.all()}
                response = self.client.post(form["action"], data=data)
                self.assertEqual(response.status_code, 303, response.text)
                db.session.remove()
                order = AnimalOrder.query.filter(AnimalOrder.uuid.notin_(before)).one()
                self.assertEqual(order.ids, ["NEW-1", "NEW-2"])
                response = self.client.get(response.headers["Location"])
                self.assertIn("IDs: NEW-1, NEW-2", response.text)

    def test_validation_errors_preserve_form_values_without_persisting_an_order(self):
        before = AnimalOrder.query.count()
        for changes, status in (({"age": "1.5"}, 400), ({"amount": "4"}, 409)):
            with self.subTest(changes=changes):
                response = self.client.post("/orders", data={**self.data, **changes, "comment": "Keep this comment"})
                self.assertEqual(response.status_code, status)
                self.assertEqual(OrderPageParser(response.text).textareas["comment"], "Keep this comment")
        response = self.client.post("/orders", data={**self.ids, "ids": "NEW-1, NEW-1"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(OrderPageParser(response.text).textareas["ids"], "NEW-1, NEW-1")
        response = self.client.post("/orders", data={**self.data, "licence": "protocol/Hidden"})
        self.assertEqual(response.status_code, 403)
        db.session.remove()
        self.assertEqual(AnimalOrder.query.count(), before)

    def test_jinja_escapes_comments_ids_and_errors(self):
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

    def test_order_routes_require_login(self):
        anonymous = self.app.test_client()
        for method, path in (("GET", "/orders"), ("POST", "/orders"),
                             ("GET", f"/orders/{self.own_uuid}"), ("POST", f"/orders/{self.own_uuid}/status")):
            with self.subTest(method=method, path=path):
                response = anonymous.open(path, method=method)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], "/login")
        self.assertEqual(self.client.get(f"/orders/{self.own_uuid}/status").status_code, 405)

    def test_review_forms_redirect_back_to_the_filtered_list_or_details(self):
        self.login(self.reviewer_email)
        response, page = self.page(user=self.other_email, status="pending")
        form = next(form for form in page.forms if form["action"].endswith("/status"))
        response = self.client.post(form["action"], data={**page.hidden_values(form), "status": "approved"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.stored_status(self.other_uuid), "approved")
        response = self.client.get(response.headers["Location"])
        page = OrderPageParser(response.text)
        self.assertEqual(page.order_rows, [])
        for select, value in (("filter-user", self.other_email), ("filter-status", "pending")):
            self.assertEqual([option["value"] for option in page.selects[select] if "selected" in option], [value])
        self.assertIn("Order approved.", response.text)
        response = self.client.get(f"/orders/{self.own_uuid}")
        page = OrderPageParser(response.text)
        form = next(form for form in page.forms if form["action"].endswith("/status"))
        response = self.client.post(form["action"], data={**page.hidden_values(form), "status": "rejected"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], f"/orders/{self.own_uuid}")
        self.assertEqual(self.stored_status(self.own_uuid), "rejected")
        response = self.client.get(response.headers["Location"])
        self.assertIn("Order rejected.", response.text)
        self.assertEqual(AnimalData.query.count(), 2)

    def test_review_rejects_invalid_decisions_and_prevents_reversals(self):
        self.login(self.reviewer_email)
        for status in (None, "pending", "other"):
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
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 409)
        self.assertEqual(self.stored_status(self.own_uuid), "pending")
        db.session.get(PAllowedMice, self.allowance_uuid).num_availible_animals = 6
        db.session.commit()
        with patch("data_manager.orders.today", return_value=datetime(2026, 11, 22)):
            self.assertEqual(self.review(self.own_uuid, "approved").status_code, 303)
        self.assertEqual(self.stored_status(self.own_uuid), "approved")

    def test_missing_configuration_blocks_approval_but_allows_rejection_and_history(self):
        self.login(self.reviewer_email)
        allowance = db.session.get(PAllowedMice, self.allowance_uuid)
        allowance.num_availible_animals = None
        db.session.commit()
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 409)
        db.session.delete(allowance)
        db.session.commit()
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 404)
        db.session.delete(db.session.get(Protocol, "protocol"))
        db.session.commit()
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 404)
        self.assertEqual(self.stored_status(self.own_uuid), "pending")
        self.assertEqual(self.review(self.own_uuid, "rejected").status_code, 303)
        self.login(self.owner_email)
        response, page = self.page()
        self.assertEqual(page.order_rows, [self.own_uuid, self.rejected_uuid])
        self.assertIn("No licences are available", response.text)

    def test_deleted_accounts_remain_filterable_and_membership_revocation_takes_effect(self):
        db.session.delete(db.session.get(User, self.other_email))
        db.session.commit()
        self.login(self.reviewer_email)
        response, page = self.page(user=self.other_email)
        self.assertEqual(page.order_rows, [self.other_uuid])
        self.assertIn(self.other_email, {option["value"] for option in page.selects["filter-user"]})
        db.session.get(User, self.reviewer_email).paw_control = False
        db.session.commit()
        response, page = self.page()
        self.assertEqual(page.order_rows, [])
        self.assertEqual(self.review(self.own_uuid, "approved").status_code, 403)

    def test_commit_failures_roll_back_creation_and_review(self):
        before = AnimalOrder.query.count()
        with patch.object(db.session, "commit", side_effect=RuntimeError("private database details")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/orders", data=self.data)
        self.assertEqual(response.status_code, 500)
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
