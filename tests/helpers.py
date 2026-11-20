"""Small shared fixtures; importing the production app would initialize its database."""
from flask import Flask, g

from data_manager.tables import db
from route_helpers import ROOT


def database_app(test, *, database_url="sqlite:///:memory:"):
    app = Flask(test.__class__.__module__, template_folder=str(ROOT / "src/templates"))
    app.config.update(SECRET_KEY="test-only", SQLALCHEMY_DATABASE_URI=database_url)
    db.init_app(app)
    context = app.app_context()
    context.push()
    test.addCleanup(context.pop)
    test.addCleanup(db.engine.dispose)
    test.addCleanup(db.session.remove)
    db.create_all()

    @app.before_request
    def clear_cached_user():
        # Tests keep an app context for database assertions. Production requests
        # get a fresh g, so reload the user for each test request as well.
        g.pop("_login_user", None)

    return app


def login_as(client, email):
    with client.session_transaction() as session:
        session["_user_id"] = email
        session["_fresh"] = True
