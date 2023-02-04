import json
import html
from flask import Flask, render_template, request, send_file, redirect, url_for
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from data_manager.dmanager import DManager, date_filled
from data_manager.tables import *
from document_creator.dcreator import DCreator
from exceptions.exceptions import ParserException
from utils.utils import (
    hash_pw, sort_query, escape, has_signature, get_signature_path, get_keys_from_config
)
from jinja2 import Environment, PackageLoader, select_autoescape
from os.path import exists as file_exists
import os
import subprocess
import tempfile
import shutil
from cryptography.fernet import Fernet

SECRET, LAB_PASSWORD = get_keys_from_config("server.config")

# Create global instance of sql-connector, data-manager and flask-app.
dmanager = DManager()
app = Flask(__name__)
app.secret_key = SECRET
login_manager = LoginManager()
login_manager.init_app(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///larkum.db"
db.init_app(app)

with app.app_context():
    # Example to remove tables
    # Create tables
    db.create_all()
    # drop_all(ALL_TABLES, False)
    # safe_all("backup")
    # load_backup("backup_2")

@login_manager.user_loader 
def user_loader(user_id): 
    """! Given *user_id*, return the associated User object.

    @param user_id  user_id (email) user to retrieve
    """
    return User.query.get(user_id)

@login_manager.unauthorized_handler
def unauthorized_handler():
    return redirect("/login")

@app.route("/")
@login_required
def main():
    """! Serves main-page showing all users, protocols. 

    @return Rendered html main-page from jinja2-template.
    """
    print("PROTOCOLS: ", dmanager.protocols())
    return render_template(
        "index.html", 
        users=dmanager.users(), 
        protocols=dmanager.protocols(),
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    """! Serves login-page.

    @return Rendered html login-page from jinja2-template.
    """
    if request.method == "GET":
        return render_template("login.html", msg="")
    # Check lab password first.
    if request.form["lab_password"] != LAB_PASSWORD:
        return render_template("login.html", msg="Lab password incorrect")
    # Get user
    user = User.query.get(request.form["email"])
    if user:
        # Get hashed password and check password.
        hashed_password, _ = hash_pw(request.form["password"], user.salt)
        if user.password == str(hashed_password):
            login_user(user)
            return redirect("/")
        return render_template("login.html", msg="Password incorrect")
    return render_template("login.html", msg="User not found")

@app.route("/register", methods=["GET", "POST"])
def register():
    """! Serves registration-page.

    @return Rendered html registration-page from jinja2-template.
    """
    if request.method == "GET":
        return render_template("register.html", msg="", users=dmanager.users())
    if User.query.get(request.form["email"]):
        return render_template("register.html", msg="User with this email already exists!")
    if request.form["password"] != request.form["password2"]:
        return render_template("register.html", msg="Passwords don't match!")
    if request.form["lab_password"] != LAB_PASSWORD:
        return render_template("register.html", msg="Lab password incorrect!")
    hashed_password, salt = hash_pw(request.form["password"])
    user = User( 
        email=request.form["email"],
        name=request.form["name"],
        password=str(hashed_password),
        salt=salt
    )
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return redirect("/")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/login")

@app.route("/overview")
@login_required
def overview():
    """! Serves general overview of all animal-data. 

    @return Rendered html overview-page from jinja2-template.
    """
    return render_template(
        "overview.html", 
        animal_data=AnimalData.query.all(),
        protocols=dmanager.protocols_and_subprotocols(),
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/users/<user>")
@login_required
def user_overview(user: str):
    """! Serves overview of all animal-data of a single user 

    @param user  the user for which to show animal-data.

    @return Rendered html user-overview page from jinja2-template.
    """
    return render_template(
        "user_overview.html", 
        user=user, 
        animal_data=AnimalData.query.filter(AnimalData.user == user),
        protocols=dmanager.protocols_and_subprotocols(),
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/protocols/<protocol>")
@login_required
def protocol_overview(protocol: str):
    """! Serves overview of all animal-data of a single protocol.

    @param protocol  the protocol for which to show animal-data.

    @return Rendered html protocol-overview page from jinja2-template.
    """
    return render_template(
        "protocol_overview.html", 
        protocol=protocol,
        animal_data=AnimalData.query.filter(AnimalData.protocol_escaped == protocol),
        protocols=dmanager.protocols_and_subprotocols(),
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/animal_data/<animal_id>", defaults={"category": ""})
@app.route("/animal_data/<animal_id>/<category>")
@login_required
def input(animal_id: str, category: str):
    """! Serves page to input experiment-data.

    @param animal_id  id of animal for which to add experiment-data.
    
    @return Rendered html experiment-data input page from jinja2-template.
    """
    animal_data = AnimalData.query.get(animal_id)
    # Redirect 
    if animal_data.user != current_user.name:
        return redirect("/")
    death_date = animal_data.death_date if date_filled(animal_data.death_date) else None
    general = General.query.get(animal_id)
    availible_viruses = PVirus.query.filter(PVirus.protocol == general.experiment)
    availible_anesthetic=PAnesthesia.query.filter(PAnesthesia.protocol == general.experiment)
    availible_analgesic=PAnalgesia.query.filter(PAnalgesia.protocol == general.experiment)
    availible_procedures=PProcedure.query.filter(PProcedure.protocol == general.experiment)

    return render_template(
        "input.html", 
        stored=True,
        general=general,
        viruses=sort_query(Virus.query.filter(Virus.animal_id == animal_id), "date"),
        anesthesia=sort_query(Anesthesia.query.filter(Anesthesia.animal_id == animal_id), "date"),
        analgesic=sort_query(Analgesia.query.filter(Analgesia.animal_id == animal_id), "date"),
        procedures=sort_query(Procedure.query.filter(Procedure.animal_id == animal_id), "start_date"),
        post_procedures=sort_query(
            PostProcedure.query.filter(PostProcedure.animal_id == animal_id), "start_date"
        ),
        availible_anesthetic=availible_anesthetic,
        availible_analgesic=availible_analgesic,
        availible_procedures=availible_procedures,
        availible_viruses=availible_viruses,
        json_anesthetic=json.dumps([table_to_json(x) for x in availible_anesthetic]),
        json_analgestic=json.dumps([table_to_json(x) for x in availible_analgesic]),
        json_procedures=json.dumps([table_to_json(x) for x in availible_procedures]),
        json_viruses=json.dumps([table_to_json(x) for x in availible_viruses]),
        animal_id=animal_id,
        animal_data=[animal_data],
        death_date=death_date,
        dob=animal_data.dob,
        protocols=dmanager.protocols_and_subprotocols(),
        notes={note.category:note.note for note in Note.query.filter(Note.animal_id == animal_id)},
        category=category,
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/settings")
@login_required
def settings():
    return render_template(
        "settings.html", user_email=current_user.email, user_name=current_user.name
    )

@app.route("/account")
@login_required
def account():
    has_sig = has_signature(current_user.name)
    registered_users = [ x.name for x in User.query.all()]
    print("registered_users: ", registered_users)
    print("pyrat users: ", dmanager.users())
    users = [(x, x in registered_users) for x in dmanager.users()]
    print("availible users: ", users)
    return render_template(
        "account.html", 
        users=users, 
        escaped_user=escape(current_user.name),
        has_signature=has_signature(current_user.name),
        user_email=current_user.email, 
        user_name=current_user.name
    )

@app.route("/account/<email>/update/username/<username>", methods=["POST"])
@login_required 
def update_username(email, username):
    user = User.query.get(email)
    if user:
        user.name = html.unescape(username)
        db.session.commit()
        return "", 200
    return "User not found", 404

@app.route("/account/<email>/delete/", methods=["POST"])
@login_required 
def delete_username(email):
    user = User.query.get(email)
    if user:
        db.session.delete(user)
        logout_user()
        return redirect("/login")
    return "User not found", 404

@app.route("/signature/<user>")
@login_required 
def get_signature(user: str):
    path, mimetype = get_signature_path(current_user.name)
    return send_file(path, mimetype = mimetype)

@app.route("/delete/signature/<escaped_user>", methods=["POST"])
@login_required 
def remove_signature(escaped_user: str):
    if has_signature(current_user.name):
        path, mimetype = get_signature_path(current_user.name)
        os.remove(f"src/{path}")
        return "", 200
    else: 
        return "no signature found", 404

@app.route("/upload/signature/<escaped_user>", methods=["POST"])
@login_required 
def upload_signature(escaped_user: str):
    remove_signature(escaped_user)
    content = request.files
    file = content.get("sig")
    if file.mimetype == "image/jpeg":
        file.save(f"src/signatures/{escaped_user}.jpg")
    else:
        file.save(f"src/signatures/{escaped_user}.png")
    return "", 200


@app.route("/settings/definitions", defaults={"category": ""})
@app.route("/settings/definitions/<category>")
@login_required
def availible(category: str):
    data = {}
    if category == "medication":
        data=sort_query(AMedication.query.all(), "days_after_surgery")
    if category == "procedures":
        data=sort_query(AProcedure.query.all(), "days_after_start")
    if category == "viruses":
        data=sort_query(AVirus.query.all(), "days_after_start")
    return render_template(
        "definitions.html", 
        user_email=current_user.email, 
        user_name=current_user.name,
        category=category,
        data=data
    )

@app.route("/settings/protocols", methods=["GET"])
@login_required
def protocols():
    return render_template(
        "protocols.html", 
        user_email=current_user.email, 
        user_name=current_user.name,
        protocols=Protocol.query.all(),
        msg=""
    )

@app.route("/settings/protocols/<escaped_protocol>", methods=["GET"])
@login_required
def protocol(escaped_protocol: str):
    protocol = Protocol.query.get(escaped_protocol)
    if protocol:
        return render_template(
            "protocol.html", 
            user_email=current_user.email, 
            user_name=current_user.name,
            protocol=protocol,
            subprotocols=protocol.get_subprotocols(),
            msg=""
        )
    return render_template(
        "protocols.html", 
        user_email=current_user.email, 
        user_name=current_user.name,
        protocols=Protocol.query.all(),
        msg="Protocol not found"
    )

@app.route("/update/animal_data/subprotocol", methods=["POST"])
@login_required
def update_animal_subprotocol(): 
    """! Updates the subprotocol of an animal and initializes experiment-data.

    @param subprotocol  the new subprotocol

    @return error-/ success-message and status code.
    """
    subprotocol = request.form.get("subprotocol")
    animal_id = request.form.get("animal_id")
    force = request.form.get("force") == "true"
    try:
        txt, status = dmanager.set_subprotocol(animal_id, subprotocol, force) 
        return txt, status
    except Exception as err: 
        _, _ = dmanager.set_subprotocol(animal_id, "---", force)
        print(traceback.format_exc())
        print(err)
        return repr(err), 500

@app.route("/update/animal_data/protocol", methods=["POST"])
@login_required
def update_animal_protocol(): 
    """! Updates the subprotocol of an animal and initializes experiment-data.

    @param subprotocol  the new subprotocol

    @return error-/ success-message and status code.
    """
    subprotocol = request.form.get("protocol")
    animal_id = request.form.get("animal_id")
    force = request.form.get("force") == "true"
    txt, status = dmanager.set_protocol(animal_id, subprotocol, force) 
    return txt, status

@app.route("/update/animal_data/sacrifice_date/<animal_id>", methods=["POST"])
@login_required
def update_animal_death_date(animal_id): 
    """! Updates the subprotocol of an animal and initializes experiment-data.

    @param subprotocol  the new subprotocol

    @return error-/ success-message and status code.
    """
    death_date = request.form.get("death_date")
    txt, status = dmanager.set_death_date(animal_id, death_date) 
    return redirect(request.referrer)


@app.route("/update/animal_data/dates/<animal_id>/<autofill>", methods=["POST"])
@login_required
def update_dates(animal_id: str, autofill: bool): 
    """! Updates the dates an animal 

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    print(f"Updateing dates: {animal_id}, {request.form['date']}")
    return dmanager.update_dates(animal_id, request.form["date"], autofill == "true")

@app.route("/update/animal_data/suffering/<animal_id>/<suffering>", methods=["POST"])
@login_required
def update_suffering(animal_id: str, suffering: str): 
    """! Updates the dates an animal 

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    print(f"Updateing suffering: {animal_id}, {suffering}")
    general = General.query.get(animal_id)
    general.suffering = suffering 
    db.session.commit()
    return "", 200


@app.route("/update/animal_data/weights/<animal_id>", methods=["POST"])
@login_required
def update_weights(animal_id: str): 
    """! Updates the weight and watercontrol of an animal 

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    weights = request.form.get("weights")
    watercontrol = request.form.get("watercontrol")
    txt, status = dmanager.update_weights_and_watercontrol(
        animal_id, weights, watercontrol
    ) 
    return txt, status


@app.route("/upload/pyrat_csv", methods=["POST"])
@login_required
def store_animal_data():
    """! Adds new animal-data from .CSV.

    @return error-/ success-message and status code.
    """
    content = request.files
    # upload via data-manager
    txt, status = dmanager.extract_animal_data(content.get("csv"))
    return txt, status

@app.route("/generate/weights/<animal_id>/<weight>", methods=["POST"])
@login_required
def generate_weight_list(animal_id: str, weight: int): 
    txt, status = dmanager.generate_weight_list(animal_id, weight)
    return txt, status

@app.route("/store/notes/<animal_id>/<category>", methods=["POST"])
@login_required
def store_notes(animal_id: str, category: str):
    """! Adds new experiment-data from for given animal-id.

    @param animal_id  ID of animal for which to add data.
    @return error-/ success-message and status code.
    """
    note_txt = request.form.get("note")
    if dmanager.store_note(animal_id, category, note_txt):
        return "Success", 200
    return "Something went wrong", 500

@app.route("/animal_data/<animal_id>/<category>", methods=["POST"])
@login_required
def update_experiment_data(animal_id: str, category: str): 
    """! Updates an entry in an animals experiment data. """
    dmanager.update_experiment_data_entry(animal_id, category, request.form)
    return redirect(request.referrer)

@app.route(
    "/animal_data/<animal_id>/delete/<category>/<name>", defaults={"date": ""}, methods=["POST"]
)
@app.route("/animal_data/<animal_id>/delete/<category>/<name>/<date>", methods=["POST"])
@login_required
def delete_experiment_data(animal_id: str, category: str, name: str, date: str): 
    """! Updates an entry in an animals experiment data. """
    name = html.unescape(name).replace("_", "/")
    dmanager.delete_experiment_data_entry(animal_id, category, name, date)
    return redirect(f"/animal_data/{animal_id}/{category}")

@app.route("/clear/<animal_id>", methods=["POST"])
@login_required
def clear_experiment_data(animal_id: str):
    """! Adds new experiment-data from for given animal-id.

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    animal_data = AnimalData.query.get(animal_id)
    dmanager.set_subprotocol(animal_id, animal_data.subprotocol, True)
    return "Success", 200

@app.route("/generate/surgery_sheet/<animal_id>", methods=["POST"])
@login_required
def generate_surgery_sheet(animal_id: str):
    animal_data = AnimalData.query.get(animal_id)
    if not date_filled(animal_data.death_date): 
        return "Animal is not yet sacrificed", 401
    dcreator = DCreator(
        template_path="templates/surgery_sheet", 
        experiment_data=dmanager.get_experiment_data(animal_id),
        animal_data=table_to_json(animal_data),
        user_email=current_user.email
    )
    dcreator.create_from_template()
    return send_file("output/surgery_sheet.docx", as_attachment=True)

@app.route("/generate/score_sheet/<animal_id>", methods=["POST"])
@login_required
def generate_score_sheet(animal_id: str):
    animal_data = AnimalData.query.get(animal_id)
    if not date_filled(animal_data.death_date): 
        return "Animal is not yet sacrificed", 401

    dcreator = DCreator(
        template_path="templates/score_sheet", 
        experiment_data=dmanager.get_experiment_data(animal_id),
        animal_data=table_to_json(animal_data),
        user_email=current_user.email
    )
    dcreator.create_score_sheet()
    return send_file("output/score_sheet.docx", as_attachment=True)

@app.route("/generate/paragraph9/<escaped_protocol>", methods=["POST"])
@login_required
def generate_paragraph_9(escaped_protocol: str):

    env = Environment(
        loader=PackageLoader("app"),
        autoescape=select_autoescape()
    )
    template = env.get_template("main.tex")
    subprotocols, protocol = dmanager.get_p9_data(escaped_protocol)
    txt = template.render(subprotocols=subprotocols, protocol=protocol)
    tmp_path = tempfile.mkdtemp() 
    full_path = f"{tmp_path}/main.tex"
    f = open(full_path, "w") 
    f.write(txt) 
    f.close()

    shutil.copy("logo.jpg", f"{tmp_path}")

    # proc=subprocess.Popen(["pdflatex", full_path]) 
    proc=subprocess.Popen(
        ["pdflatex", full_path], 
        cwd=tmp_path, 
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.STDOUT
    )
    proc.communicate()
    return send_file(f"{tmp_path}/main.pdf", as_attachment=True)


@app.route("/settings/definitions/<category>", methods=["POST"])
@login_required 
def update_definitions_entry(category: str):
    dmanager.update_definitions_entry(category, request.form)
    return redirect(request.referrer)

@app.route("/definitions/delete/<category>/<name>", methods=["POST"])
@login_required 
def delete_definition(category: str, name: str): 
    name = html.unescape(name).replace("_", "/")
    dmanager.delete_definitions_entry(category, name)
    return redirect(f"/settings/definitions/{category}")

@app.route("/settings/protocols/<protocol>/<subprotocol>/<category>", methods=["POST"])
@login_required 
def update_protocol_entry(protocol: str, subprotocol: str, category: str):
    dmanager.update_protocol_entry(
        category, f"{protocol}/{subprotocol}", request.form
    )
    return redirect(request.referrer)

@app.route("/settings/protocols/delete/<category>/<uuid>", methods=["POST"])
@login_required 
def delete_protocol_entry(category: str, uuid: str): 
    dmanager.delete_protocol_entry(category, uuid)
    return redirect(request.referrer)

@app.route("/settings/protocols/<escaped_protocol>/<subprotocol>/<category>")
@login_required
def subprotocol(escaped_protocol: str, subprotocol: str, category: str):
    protocol = Protocol.query.get(escaped_protocol)
    full_protocol = f"{escaped_protocol}/{subprotocol}"
    data, definitions = dmanager.get_protocol_data(category, full_protocol)
    if protocol:
        return render_template(
            "subprotocol.html", 
            user_email=current_user.email, 
            user_name=current_user.name,
            protocol=protocol,
            subprotocol=subprotocol,
            category=category,
            data=data,
            definitions=definitions,
            json_definitions=json.dumps([table_to_json(x) for x in definitions]), 
            msg=""
        )

@app.route("/settings/add_protocol", methods=["POST"]) 
@login_required 
def add_protocal():
    escaped_name = escape(request.form["name"]).strip()
    protocol = Protocol.query.get(escaped_name)
    if protocol:
        return render_template(
            "protocols.html", 
            user_email=current_user.email, 
            user_name=current_user.name,
            protocols=Protocol.query.all(),
            msg="A protocol with this name already exists!"
        )

    protocol = Protocol(
        name=request.form["name"],
        escaped=escaped_name,
        subprotocols=""
    )
    db.session.add(protocol)
    db.session.commit()
    return redirect("/settings/protocols")

@app.route("/settings/protocols/<escaped_protocol>/add_protocol", methods=["POST"]) 
@login_required 
def add_subprotocal(escaped_protocol):
    protocol = Protocol.query.get(escaped_protocol)
    subprotocol = request.form["name"]
    if not protocol:
        return render_template(
            "protocols.html", 
            user_email=current_user.email, 
            user_name=current_user.name,
            protocols=Protocol.query.all(),
            msg="Matching protocol does not exist!"
        )
    if subprotocol in protocol.get_subprotocols(): 
        return render_template(
            "protocol.html", 
            user_email=current_user.email, 
            user_name=current_user.name,
            protocol=protocol,
            msg="Subprotocol already exists!"
        )

    protocol.add_subprotocol(subprotocol)
    db.session.commit()
    return redirect("/settings/protocols/" + escaped_protocol)

@app.route("/settings/protocols/remove/<escaped_protocol>", methods=["POST"]) 
@login_required 
def remove_protocol(escaped_protocol):
    protocol = Protocol.query.get(escaped_protocol)

    # Delete all data matchin protocol:
    general = PGeneral.query.get(escaped_protocol)
    if general: 
        db.session.delete(general)
    for Table in PROTOCOL_TABLES.values(): 
        entries = Table.query.filter(Table.protocol == escaped_protocol)
        if entries.first(): 
            for entry in entries:
                db.session.delete(Table.query.get((escaped_protocol, entry.name)))
    # Remove protocol.
    db.session.delete(protocol)
    db.session.commit()
    return redirect("/settings/protocols")

@app.route("/settings/protocols/remove/<escaped_protocol>/<subprotocol>", methods=["POST"]) 
@login_required 
def remove_subprotocol(escaped_protocol, subprotocol):
    protocol = Protocol.query.get(escaped_protocol)
    if not protocol:
        return render_template(
            "protocols.html", 
            user_email=current_user.email, 
            user_name=current_user.name,
            protocols=Protocol.query.all(),
            msg="Matching protocol does not exist!"
        )
    if subprotocol not in protocol.get_subprotocols(): 
        return render_template(
            "protocol.html", 
            user_email=current_user.email, 
            user_name=current_user.name,
            protocol=protocol,
            msg="Subprotocol does not exists!"
        )

    protocol.remove_subprotocol(subprotocol)
    db.session.commit()
    return redirect("/settings/protocols/" + escaped_protocol)

if __name__=="__main__":
    app.run(debug=True)
