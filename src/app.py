import json
import html
from flask import (
    Flask, render_template, make_response, jsonify, request, send_file,
    redirect, session
)
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from data_manager.dmanager import DManager, date_filled
from data_manager.tables import *
from document_creator.dcreator import DCreator, GenerationThread
from exceptions.exceptions import *
import os
import subprocess
import re
import tempfile
import traceback
import shutil
from functools import wraps
from utils.utils import *
from utils.dt_utils import * 

SIGNATURE_PATH = "src/signatures/"
SERVER_CONFIG_PATH = "server.config"
SECRET, LAB_PASSWORD = get_keys_from_config(SERVER_CONFIG_PATH)

REL_BACKUP_PATH = "backups/"
BACKUP_PATH = f"src/{REL_BACKUP_PATH}/"
DB_PATH = "instance/larkum.db"

generation_threads = {}

# Create global instance of sql-connector, data-manager and flask-app.
dmanager = DManager()
app = Flask(__name__)
app.secret_key = SECRET
login_manager = LoginManager()
login_manager.init_app(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///larkum.db"
db.init_app(app)

def handle_exception(func): 
    @wraps(func)
    def wrapper(*args, **kwargs):
        try: 
            return func(*args, **kwargs)
        except ParserException as error:
            print(traceback.format_exc())
            return error.msg, error.status
        except Exception as error:
            print(traceback.format_exc())
            return repr(error), 500
    return wrapper

def create_root_user_if_not_exists():
    root_email = get_root_user(SERVER_CONFIG_PATH)
    root = User.query.get(root_email)
    if not root: 
        root_password = getpass.getpass("Create admin user password: ")
        hashed_password, salt = hash_pw(root_password)
        print(f"root_email: '{root_email}'")
        user = User( 
            email=root_email,
            name="guest",
            admin=True,
            password=str(hashed_password),
            salt=salt
        )
        db.session.add(user)
        db.session.commit()

def update_lines():
    # Update availible lines
    with open("resources/lines.json") as f:
        lines = json.load(f)
        for line in lines: 
            if not ALine.query.get(line): 
                line = ALine(line)
                db.session.add(line)
        db.session.commit()

def create_backup(): 
    shutil.copyfile(
        DB_PATH,
        f"{BACKUP_PATH}/backup_{datetostr(today(), DATE_TIME)}.db"
    )

with app.app_context():
    # Example to remove tables
    # Create tables
    db.create_all()

    # DROP all experiment and animal data:
    create_root_user_if_not_exists()
    update_lines()
    # Remove invalid subprotocols
    # Protocol.query.get("G0278_16").remove_subprotocol("G 0278/16 4.3")
    db.session.commit()


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
    return render_template(
        "index.html", 
        users=dmanager.pyrat_usernames(), 
        protocols=dmanager.protocols(),
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
        return render_template("register.html", msg="")
    if not re.match("[^@]+@[^@]+\.[^@]+", request.form["email"]):
        return render_template("register.html", msg="Not a valid E-Mail adress!")
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
        admin=False,
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
    # Apply filter,  sort (and reverse)
    reverse = request.args.get("reverse", default="False", type=str)
    animal_data = dmanager.get_overview_table(
        initial_query=AnimalData.query,
        sort_by=request.args.get("sort_by", default="dob", type=str),
        reverse=reverse,
        filter_date=request.args.get("range", default="", type=str),
        start=request.args.get("from", default="", type=str),
        end=request.args.get("to", default="", type=str),
        mla_num=request.args.get("id", default="", type=str),
    )
    return render_template(
        "overview.html", 
        animal_data=animal_data,
        start_dates=dmanager.get_start_dates(animal_data),
        protocols=dmanager.protocols_and_subprotocols(),
        args=request.args,
        reverse="True" if reverse == "False" else "False"
    )

@app.route("/users/<user>")
@login_required
def user_overview(user: str):
    """! Serves overview of all animal-data of a single user 

    @param user  the user for which to show animal-data.

    @return Rendered html user-overview page from jinja2-template.
    """
    # Apply filter,  sort (and reverse)
    reverse = request.args.get("reverse", default="False", type=str)
    animal_data = dmanager.get_overview_table(
        initial_query=AnimalData.query.filter(AnimalData.user == user),
        sort_by=request.args.get("sort_by", default="dob", type=str),
        reverse=reverse,
        filter_date=request.args.get("range", default="", type=str),
        start=request.args.get("from", default="", type=str),
        end=request.args.get("to", default="", type=str),
        mla_num=request.args.get("id", default="", type=str),
    )
    return render_template(
        "user_overview.html", 
        user=user, 
        start_dates=dmanager.get_start_dates(animal_data),
        animal_data=animal_data,
        protocols=dmanager.protocols_and_subprotocols(),
        args=request.args,
        reverse="True" if reverse == "False" else "False"
    )

@app.route("/protocols/<protocol>")
@login_required
def protocol_overview(protocol: str):
    """! Serves overview of all animal-data of a single protocol.

    @param protocol  the protocol for which to show animal-data.

    @return Rendered html protocol-overview page from jinja2-template.
    """
    # Apply filter,  sort (and reverse)
    reverse = request.args.get("reverse", default="False", type=str)
    animal_data = dmanager.get_overview_table(
        initial_query=AnimalData.query.filter(AnimalData.protocol_escaped == protocol),
        sort_by=request.args.get("sort_by", default="dob", type=str),
        reverse=reverse,
        filter_date=request.args.get("range", default="", type=str),
        start=request.args.get("from", default="", type=str),
        end=request.args.get("to", default="", type=str),
        mla_num=request.args.get("id", default="", type=str),
    )
    return render_template(
        "protocol_overview.html", 
        protocol=protocol,
        animal_data=animal_data,
        start_dates=dmanager.get_start_dates(animal_data),
        protocols=dmanager.protocols_and_subprotocols(),
        args=request.args,
        reverse="True" if reverse == "False" else "False"
    )

@app.route('/table/<area>/', defaults={'what': ""})
@app.route("/table/<area>/<what>")
@login_required
def overview_table(area: str, what: str):
    if area == "users": 
        initial_request = AnimalData.query.filter(AnimalData.user == what)
    elif area == "protocols":
        initial_request = AnimalData.query.filter(AnimalData.protocol_escaped == what)
    else: 
        initial_request = AnimalData.query
                                                  
    # Apply filter,  sort (and reverse)
    reverse = request.args.get("reverse", default="False", type=str)
    animal_data = dmanager.get_overview_table(
        initial_query=initial_request,
        sort_by=request.args.get("sort_by", default="dob", type=str),
        reverse=reverse,
        filter_date=request.args.get("range", default="", type=str),
        start=request.args.get("from", default="", type=str),
        end=request.args.get("to", default="", type=str),
        mla_num=request.args.get("id", default="", type=str),
    )
    return render_template(
        "overview_table.html", 
        protocol=protocol,
        animal_data=animal_data,
        start_dates=dmanager.get_start_dates(animal_data),
        protocols=dmanager.protocols_and_subprotocols(),
        args=request.args,
        reverse="True" if reverse == "False" else "False"
    )

@app.route("/animal_data/delete/<animal_id>", methods=["POST"])
@login_required
def delete_animal_data(animal_id: str): 
    """! Updates an entry in an animals experiment data. """
    if "," not in animal_id:
        text, status = dmanager.delete_animal_data(animal_id)
    else: 
        for x in animal_id.split(","): 
            text, status = dmanager.delete_animal_data(x)
    return text, status

@app.route("/animal_data/reset/", methods=["POST"])
@login_required
def reset_animal_data(): 
    """! Updates an entry in an animals experiment data. """
    data_reset = dmanager.reset_animal_data(request.form["experiment"])
    return str(data_reset), 200

@app.route("/animal_data/reload/", methods=["POST"])
@login_required
def reload_animal_data(): 
    """! Updates an entry in an animals experiment data. """
    response = dmanager.reload_animal_data(request.form["experiment"])
    return make_response(jsonify(response), 200)

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
    if animal_data.user != current_user.name and not current_user.admin:
        return redirect("/")
    death_date = animal_data.death_date if date_filled(animal_data.death_date) else None
    general = General.query.get(animal_id)
    availible_viruses = sort_query(PVirus.query.filter(PVirus.protocol == general.experiment), "name")
    availible_medication= sort_query(
        PMedication.query.filter(PMedication.protocol == general.experiment), "name"
    )
    availible_procedures=sort_query(
        PProcedure.query.filter(PProcedure.protocol == general.experiment), "name"
    )
    allowed_users = [] 
    protocol_general = PGeneral.query.filter(PGeneral.protocol == general.experiment)
    if protocol_general.first(): 
        allowed_users = protocol_general.first().allowed_users.split(", ")

    # Create ref to previous page
    ref = False
    if "/users/" in request.referrer or "/protocols/" in request.referrer: 
        ref_name = html.unescape(request.referrer[request.referrer.rfind("/")+1:])
        ref = {"name": ref_name, "link": request.referrer}

    durations = {str(p.uuid):p.get_duration() for p in availible_procedures}

    age = len(daterange_str(animal_data.dob, general.start)) if date_filled(general.start) else 15
    return render_template(
        "input.html", 
        stored=True,
        general=general,
        start_dates=dmanager.get_start_dates([animal_data]),
        medication=sort_query(Medication.query.filter(Medication.animal_id == animal_id), "name"),
        viruses=sort_query(Virus.query.filter(Virus.animal_id == animal_id), "name"),
        procedures=sort_query(Procedure.query.filter(Procedure.animal_id == animal_id), "start_date"),
        availible_medication=availible_medication,
        availible_procedures=availible_procedures,
        availible_viruses=availible_viruses,
        availible_kinds=sort_query(AKind.query.all(), "name"),
        json_medication=json.dumps([table_to_json(x) for x in availible_medication]),
        json_procedures=json.dumps([table_to_json(x) for x in availible_procedures]),
        json_viruses=json.dumps([table_to_json(x) for x in availible_viruses]),
        durations=durations,
        allowed_users=allowed_users,
        animal_id=animal_id,
        animal_data=[animal_data],
        death_date=death_date,
        dob=animal_data.dob,
        protocols=dmanager.protocols_and_subprotocols(),
        notes={note.category:note.note for note in Note.query.filter(Note.animal_id == animal_id)},
        age=age,
        last_weight=int(json.loads(general.weights)[-1]) if len(general.weights) > 2 else 5,
        category=category,
        ref=ref, 
        args=request.args,
    )

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

@app.route("/settings/user-management")
@login_required
def user_management():
    if not current_user.admin:
        return redirect("/") 
    registered_users = [ x.name for x in User.query.all()]
    availible_usernames = [(x, x in registered_users) for x in dmanager.pyrat_usernames()]
    return render_template(
        "user_management.html", 
        users=sort_query(User.query.all(), "name"),
        availible_usernames=availible_usernames
    )

@app.route("/user_management/update_username", methods=["POST"])
@login_required
def update_use_username():
    return dmanager.update_responsible(
        request.form.get('old_username'), request.form.get('new_username')
    )

@app.route("/account")
@login_required
def account():
    registered_users = [ x.name for x in User.query.all()]
    availible_usernames= [(x, x in registered_users) for x in dmanager.pyrat_usernames()]
    return render_template(
        "account.html", 
        availible_usernames=availible_usernames, 
        escaped_user=escape(current_user.name),
        has_signature=has_signature(current_user.name),
    )

@app.route("/settings/backup-management")
@login_required
def backup():
    # Walk through the directory tree and append subdirectory paths to the list
    backups = []
    for backup in os.listdir(BACKUP_PATH):
        backup_path = os.path.join(BACKUP_PATH, backup)
        if os.path.isfile(backup_path) and backup != ".keep":
            backups.append(backup)
    backups.sort()
    backups.reverse()
    return render_template("backup_management.html", backups=backups)

@app.route("/account/<email>/update/username/<username>", methods=["POST"])
@login_required 
def update_username(email, username):
    user = User.query.get(email)
    if user:
        user.name = html.unescape(username)
        db.session.commit()
        return "", 200
    return "User not found", 404

@app.route("/account/<email>/delete", methods=["POST"])
@login_required 
def delete_username(email):
    if not current_user.admin and email != current_user.email:
        return "Only admins can delete accounts of other users", 403
    user = User.query.get(email)
    if user:
        db.session.delete(user)
        db.session.commit()
        if request.args.get("logout"):
            logout_user()
        return redirect("/login")
    return "User not found", 404

@app.route("/account/<email>/set_admin", methods=["POST"])
@login_required 
def change_admin_status(email):
    if not current_user.admin:
        return "Only admins can change admin status of other users", 403
    user = User.query.get(email)
    if user:
        is_admin = request.args.get("admin")
        user.admin = request.args.get("admin") == "True"
        db.session.commit()
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
    return render_template(
        "definitions.html", 
        category=category,
        viruses=sort_query(AVirus.query.all(), "name"),
        procedures=sort_query(AProcedure.query.all(), "name"),
        kinds=sort_query(AKind.query.all(), "name"),
        lines=sort_query(ALine.query.all(), "name"),
        medications=sort_query(AMedication.query.all(), "name")
    )

@app.route("/settings/protocols", methods=["GET"])
@login_required
def protocols():
    return render_template(
        "protocols.html", 
        protocols=sort_query(Protocol.query.all(), "name"),
        is_setup=dmanager.protocol_is_setup,
        msg=""
    )

@app.route("/settings/protocols/<escaped_protocol>", methods=["GET"])
@login_required
def protocol(escaped_protocol: str):
    protocol = Protocol.query.get(escaped_protocol)
    if protocol:
        return render_template(
            "protocol.html", 
            protocol=protocol,
            subprotocols=protocol.get_subprotocols(),
            is_setup=dmanager.subprotocol_is_setup,
            msg=""
        )
    return render_template(
        "protocols.html", 
        protocols=Protocol.query.all(),
        is_setup=dmanager.protocol_is_setup,
        msg="Protocol not found"
    )

@app.route("/settings/backups/add", methods=["POST"])
@login_required
def add_backup(): 
    create_backup()
    return "", 200

@app.route("/settings/backups/delete/<backup>", methods=["POST"])
@login_required
def delete_backup(backup: str): 
    os.remove(f"{BACKUP_PATH}/{backup}")
    return "", 200

@app.route("/settings/backups/download/<backup>", methods=["POST"])
@login_required
def download_backup(backup: str): 
    return send_file(f"{REL_BACKUP_PATH}/{backup}", as_attachment=True)

@app.route("/settings/backups/load/<backup>", methods=["POST"])
@login_required
def load_backup(backup: str): 
    create_backup()
    shutil.copyfile(f"{BACKUP_PATH}/{backup}", DB_PATH)
    return "", 200

@app.route("/update/animal_data/all", methods=["POST"])
@login_required
def update_animal_all(): 
    txt = "failed"
    status = 400
    try:
        animal_id = request.form.get("animal_id")
        txt, status, _ = dmanager.set_protocol(animal_id, request.form.get("protocol"), False) 
        txt, status = dmanager.set_subprotocol(animal_id, request.form.get("subprotocol"), False) 
        txt, status = dmanager.update_dates(animal_id, request.form.get("start"), True)
        if date_filled(request.form.get("end")):
            txt, status = dmanager.set_death_date(animal_id, request.form.get("end"))
        return txt, status
    except Exception as err: 
        return txt + repr(err), status


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
    except AttributeError as err: 
        _, _ = dmanager.set_subprotocol(animal_id, "---", force)
        return ("Could not set protocol. Maybe your protocol is missing some entries" 
             " (also check General and Watercontrol)"), 400
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
    protocol = request.form.get("protocol")
    animal_id = request.form.get("animal_id")
    force = request.form.get("force") == "true"
    txt, status, _ = dmanager.set_protocol(animal_id, protocol, force) 
    return txt, status

@app.route("/update/animal_data/protocol/live", methods=["POST"])
@login_required
def update_animal_protocol_live(): 
    """! Updates the subprotocol of an animal and initializes experiment-data.
    Live in the sence, that it responds with the now availible subprotocols,
    which can be added to the sub-protocol dropdown "live".

    @param subprotocol  the new subprotocol

    @return error-/ success-message and status code.
    """
    protocol = request.form.get("protocol")
    animal_id = request.form.get("animal_id")
    txt, status, escaped_protocol = dmanager.set_protocol(animal_id, protocol, False) 
    if status == 200:
        protocol = Protocol.query.get(escaped_protocol)
        if protocol:
            response = {"subprotocols": protocol.get_subprotocols()}
            return make_response(jsonify(response), status)
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
@handle_exception
def update_dates(animal_id: str, autofill: bool): 
    """! Updates the dates an animal 

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    return dmanager.update_dates(animal_id, request.form["start"], autofill == "true")
    # exception handled

@app.route("/update/animal_data/suffering/<animal_id>/<suffering>", methods=["POST"])
@login_required
def update_suffering(animal_id: str, suffering: str): 
    """! Updates the dates an animal 

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
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
@handle_exception
def store_animal_data():
    """! Adds new animal-data from .CSV.

    @return error-/ success-message and status code.
    """
    content = request.files
    # upload via data-manager
    response, status = dmanager.extract_animal_data(
        content.get("csv"), request.form.get("ignore_comment")=="true"
    )
    return make_response(jsonify(response), status)

@app.route("/generate/weights/<animal_id>/<weight>", methods=["POST"])
@login_required
@handle_exception
def generate_weight_list(animal_id: str, weight: int): 
    return dmanager.generate_weight_list(animal_id, weight)

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
    # exception handled

@app.route("/animal_data/<animal_id>/<category>", methods=["POST"])
@login_required
@handle_exception
def update_experiment_data(animal_id: str, category: str): 
    """! Updates an entry in an animals experiment data. """
    dmanager.update_experiment_data_entry(animal_id, category, request.form)
    return "", 200
    # exception handled

@app.route("/animal_data/<animal_id>/delete/<category>/<uuid>", methods=["POST"])
@login_required
def delete_experiment_data(animal_id: str, category: str, uuid: str): 
    """! Updates an entry in an animals experiment data. """
    dmanager.delete_experiment_data_entry(category, uuid)
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

@app.route("/generate/surgery_sheet/<animal_id>")
@login_required
def generate_surgery_sheet(animal_id: str):
    animal_data = AnimalData.query.get(animal_id)
    if not date_filled(animal_data.death_date): 
        return "Animal is not yet sacrificed", 401
    dcreator = DCreator(
        template_path="templates/surgery_sheet", 
        experiment_data=dmanager.get_surgery_sheet_data(animal_id),
        animal_data=table_to_json(animal_data),
        user_email=current_user.email
    )
    dcreator.create_from_template()
    return send_file("output/surgery_sheet.docx", as_attachment=True)

@app.route("/generate/score_sheet/<animal_id>")
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
    global generation_threads
    thread_id = f"score_sheet_{animal_id}"
    generation_threads[thread_id] = GenerationThread(
        target=dcreator.create_score_sheet, dcreator=dcreator
    )
    generation_threads[thread_id].start()
    generation_threads[thread_id].join()
    del generation_threads[thread_id]
    return send_file("output/score_sheet.docx", as_attachment=True)

@app.route("/generate/paragraph9/<escaped_protocol>", methods=["POST"])
@app.route("/generate/paragraph9/<escaped_protocol>/<force>", methods=["POST"])
@login_required
@handle_exception
def generate_paragraph_9(escaped_protocol: str, force: str=""):
    subprotocols, protocol = dmanager.get_p9_data(escaped_protocol, force == "force")
    def safe(txt: str) -> str: 
        for c in ["#", "$", "%", "~", "_", "^"]:
            txt = txt.replace(c, f"\{c}")
        return txt
    txt = render_template(
        "main.tex", subprotocols=subprotocols, protocol=protocol, safe=safe
    )
    tmp_path = tempfile.mkdtemp() 
    full_path = f"{tmp_path}/main.tex"
    f = open(full_path, "w") 
    f.write(txt) 
    f.close()

    # Copy images to temp location
    shutil.copy("logo.jpg", f"{tmp_path}")
    for filename in os.listdir(SIGNATURE_PATH):
        f = os.path.join(SIGNATURE_PATH, filename)
        # checking if it is a file
        if os.path.isfile(f):
            shutil.copy(f, f"{tmp_path}")

    # proc=subprocess.Popen(["pdflatex", full_path]) 
    proc=subprocess.Popen(
        ["pdflatex", full_path], 
        cwd=tmp_path, 
        # stdout=subprocess.DEVNULL,
        # stderr=subprocess.STDOUT
    )
    proc.communicate()
    return send_file(f"{tmp_path}/main.pdf", as_attachment=True)
    # exception handled

@app.route("/generate/progress/<thread_id>")
@login_required
def generation_progress(thread_id: str): 
    global generation_threads
    if thread_id in generation_threads:
        return make_response(
            jsonify(generation_threads[thread_id].progress()), 200
        )
    return {}, 404

@app.route("/settings/definitions/<category>", methods=["POST"])
@login_required 
@handle_exception
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
@handle_exception
def update_protocol_entry(protocol: str, subprotocol: str, category: str):
    dmanager.update_protocol_entry(
        category, f"{protocol}/{subprotocol}", request.form
    )
    session["subprotocol_changed"] = True
    return "", 200
    # exception handled

@app.route("/settings/protocols/delete/<category>/<uuid>", methods=["POST"])
@login_required 
def delete_protocol_entry(category: str, uuid: str): 
    dmanager.delete_protocol_entry(category, uuid)
    session["subprotocol_changed"] = True
    return "", 200

@app.route("/settings/protocols/<escaped_protocol>/<subprotocol>/<category>")
@login_required
def subprotocol(escaped_protocol: str, subprotocol: str, category: str):
    protocol = Protocol.query.get(escaped_protocol)
    full_protocol = f"{escaped_protocol}/{subprotocol}"
    data, definitions = dmanager.get_protocol_data(category, full_protocol)
    procedures = PProcedure.query.filter(PProcedure.protocol == full_protocol)
    if procedures.first(): 
        procedures = sort_query(procedures, "name")
    if protocol:
        subprotocol_changed = session.get("subprotocol_changed")
        session.pop("subprotocol_changed", None)
        return render_template(
            "subprotocol.html", 
            protocol=protocol,
            subprotocol=subprotocol,
            category=category,
            data=data,
            definitions=definitions,
            procedures=procedures,
            kinds=AKind.query.all(),
            json_definitions=json.dumps([table_to_json(x) for x in definitions]), 
            users=dmanager.pyrat_usernames(), 
            subprotocol_changed=subprotocol_changed,
            protocol_is_setup=dmanager.subprotocol_is_setup(full_protocol),
            has_sacrifice_procedure=dmanager.has_sacrifice_procedure(full_protocol),
            missing_required_medication=dmanager.missing_required_medication(full_protocol),
            missing_required_virus=dmanager.missing_required_virus(full_protocol),
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
            protocols=Protocol.query.all(),
            is_setup=dmanager.protocol_is_setup,
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
            protocols=Protocol.query.all(),
            is_setup=dmanager.protocol_is_setup,
            msg="Matching protocol does not exist!"
        )
    if " " in subprotocol or subprotocol in protocol.get_subprotocols():
        if " " in subprotocol:
            msg = f"Subprotocol must not contain whitespaces: {subprotocol}"
        else: 
            msg = "Subprotocol already exists!"
        return render_template(
            "protocol.html", 
            protocol=protocol,
            subprotocols=protocol.get_subprotocols(),
            is_setup=dmanager.subprotocol_is_setup,
            msg=msg
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
            protocols=Protocol.query.all(),
            is_setup=dmanager.protocol_is_setup,
            msg="Matching protocol does not exist!"
        )
    if subprotocol not in protocol.get_subprotocols(): 
        return render_template(
            "protocol.html", 
            protocol=protocol,
            is_setup=dmanager.subprotocol_is_setup,
            msg="Subprotocol does not exists!"
        )

    protocol.remove_subprotocol(subprotocol)
    db.session.commit()
    return redirect("/settings/protocols/" + escaped_protocol)

if __name__=="__main__":
    app.run(debug=True)
