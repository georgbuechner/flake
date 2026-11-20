"""Exercise the overview copy/paste flow in Chromium against an in-memory database.

Start chromedriver --port=9516, then run:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tests/browser_experiment_copy.py
"""
import contextlib
import io
import json
import threading
import time
from base64 import b64decode
from pathlib import Path
from urllib.request import Request, urlopen

from flask import redirect, session
from werkzeug.serving import make_server

from data_manager.tables import AnimalData, General, PProcedure, Procedure, db
from route_helpers import ROOT
from test_experiment_copy import ExperimentCopyTests


def webdriver(path, data=None, method=None):
    request = Request("http://127.0.0.1:9516" + path,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json"}, method=method)
    with urlopen(request, timeout=20) as response:
        value = json.load(response)["value"]
    if isinstance(value, dict) and "error" in value:
        raise AssertionError(value)
    return value


def main():
    case = ExperimentCopyTests()
    driver = None
    server = None
    with contextlib.redirect_stdout(io.StringIO()):
        case.setUp()
    try:
        case.app.static_folder = str(ROOT / "src/static")
        for animal_id in ("B", "C"):
            db.session.get(AnimalData, animal_id).death_date = ""
        db.session.get(General, "B").start = ""
        db.session.add(AnimalData({
            "id": "ready", "sex": "m", "line": "Line", "dob": "2024-01-01",
            "death_date": "2025-03-20", "user": "Tester", "protocol_pyrat": "P",
            "protocol_escaped": "P", "protocol": "Protocol", "subprotocol": "S", "supplier": "",
        }))
        general = General("ready", "P/S", False, "Leicht")
        general.start = "2025-03-01"
        db.session.add(general)
        sacrifice = PProcedure("P/S", "Sacrifice", "-1", "1", False, False, 0, 0)
        db.session.add(sacrifice)
        db.session.add(Procedure("source", "Sacrifice", "2025-12-31", "2025-12-31", "Performer", sacrifice.uuid))
        db.session.commit()
        before = case.snapshot()

        @case.app.get("/__browser_test_login")
        def browser_login():
            session["_user_id"] = "tester@example.org"
            session["_fresh"] = True
            return redirect("/overview")

        server = make_server("127.0.0.1", 0, case.app)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        driver = webdriver("/session", {"capabilities": {"alwaysMatch": {
            "browserName": "chrome", "pageLoadStrategy": "eager",
            "goog:chromeOptions": {"args": ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                                             "--window-size=1440,1100",
                                             "--host-resolver-rules=MAP cdn.jsdelivr.net ~NOTFOUND, MAP fonts.googleapis.com ~NOTFOUND"]},
        }}})["sessionId"]
        prefix = "/session/" + driver

        def execute(script):
            return webdriver(prefix + "/execute/sync", {"script": script, "args": []})

        def wait_for(script):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if execute(script):
                    return
                time.sleep(0.05)
            raise AssertionError("Timed out: " + script)

        webdriver(prefix + "/url", {"url": f"http://127.0.0.1:{server.server_port}/__browser_test_login"})
        wait_for("return !!document.getElementById('experiment-copy-mode')")
        execute("""
          document.querySelector('[name=mark_animal][animal_id=source]').click();
          document.getElementById('open-experiment-copy').click();
        """)
        wait_for("return document.getElementById('experiment-copy-dialog').open")
        assert execute("return document.getElementById('experiment-copy-count-procedures').textContent") == "3"
        execute("document.getElementById('experiment-copy-form').requestSubmit()")
        assert execute("return document.getElementById('experiment-paste-mode').checked")
        assert execute("return document.querySelectorAll('[name=mark_animal]:checked').length") == 0
        execute("""
          for (const id of ['B', 'C', 'ready']) document.querySelector(`[animal_id='${id}'][name=mark_animal]`).click();
          document.getElementById('experiment-copy-mode').click();
        """)
        assert execute("return document.getElementById('open-experiment-copy').disabled")
        execute("document.getElementById('experiment-paste-mode').click(); document.getElementById('open-experiment-paste').click()")
        wait_for("return document.getElementById('experiment-paste-dialog').open")
        assert execute("return document.getElementById('confirm-experiment-paste').disabled")
        assert execute("return getComputedStyle(document.querySelector('[data-animal-id=ready]')).backgroundColor") == "rgb(210, 234, 214)"
        assert execute("return getComputedStyle(document.querySelector('[data-animal-id=B]')).backgroundColor") == "rgb(245, 212, 214)"
        execute("""
          const row = document.querySelector('[data-animal-id=B]');
          for (const button of row.querySelectorAll('button')) button.click();
        """)
        assert execute("return document.querySelector('[data-animal-id=B] [data-date-field=start]').value") == "2025-01-01"
        assert execute("return document.querySelector('[data-animal-id=B] [data-date-field=sacrifice_date]').value") == "2025-12-31"
        execute("""
          const row = document.querySelector('[data-animal-id=B]');
          row.querySelector('[data-date-field=start]').value = '2025-02-01';
          row.querySelector('[data-date-field=sacrifice_date]').value = '2025-02-20';
          row.querySelector('input').dispatchEvent(new Event('input', {bubbles:true}));
          document.querySelector('[data-animal-id=C] [data-skip-animal]').click();
        """)
        assert execute("return document.getElementById('experiment-paste-form').checkValidity()")
        assert execute("return document.getElementById('experiment-paste-ready').textContent") == "2 ready, 0 need dates, 1 skipped."
        assert not execute("return document.getElementById('confirm-experiment-paste').disabled")
        screenshot = Path("/tmp/flake-copy-paste-review.png")
        screenshot.write_bytes(b64decode(webdriver(prefix + "/screenshot")))
        execute("window.alert = () => {}; document.getElementById('experiment-paste-form').requestSubmit()")
        wait_for("return !document.getElementById('experiment-paste-dialog').open")
        assert not execute("return document.getElementById('error_modal').open")
        db.session.remove()
        assert db.session.get(General, "B").start == "2025-02-01"
        assert db.session.get(AnimalData, "B").death_date == "2025-02-20"
        assert Procedure.query.filter_by(animal_id="B", name="Surgery").one().start_date == "2025-02-03"
        assert Procedure.query.filter_by(animal_id="B", name="Sacrifice").one().start_date == "2025-02-20"
        assert Procedure.query.filter_by(animal_id="ready", name="Sacrifice").one().start_date == "2025-03-20"
        after = case.snapshot()
        for key, value in before.items():
            if key[1] in ("source", "C"):
                assert after[key] == value, key
        print("Chromium overview copy/paste, mode switching, date colors/source/manual entry, skipping and saved rows passed")
        print("Review screenshot: " + str(screenshot))
    finally:
        if driver is not None:
            webdriver("/session/" + driver, method="DELETE")
        if server is not None:
            server.shutdown()
            server.server_close()
        case.doCleanups()


if __name__ == "__main__":
    main()
