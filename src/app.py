import json
import html
from flask import Flask, render_template, request, send_file, redirect, url_for
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from data_manager.dmanager import DManager, escape_protocol, date_filled
from data_manager.sql_connector import SqlConnector
from data_manager.tables import (
    User, 
    AMedication, AProcedure, AVirus,
    PAnesthesia, PAnalgesia, PProcedure, PVirus, PWatercontrol,
    General, Anesthesia, Analgesia, Procedure, PostProcedure, Virus,
    Protocol, 
    db,
    table_to_json
)
from document_creator.dcreator import DCreator
from exceptions.exceptions import ParserException
from utils.utils import hash_pw, sort_query

# Create global instance of sql-connector, data-manager and flask-app.
sql_connector = SqlConnector("data/database.db", "resources/tables.json")
dmanager = DManager(sql_connector)
app = Flask(__name__)
app.secret_key = 'super secret string'  # Change this!
login_manager = LoginManager()
login_manager.init_app(app)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///larkum.db"
db.init_app(app)
with app.app_context():
    # Create tables
    # Anesthesia.__table__.drop(db.engine)
    # Analgesia.__table__.drop(db.engine)
    db.create_all()

LARKUM_PASSWORD = "larkum"

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
        "index.html", users=dmanager.users(), 
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
    user = User.query.get(request.form["email"])
    if user:
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
    if request.form["lab_password"] != LARKUM_PASSWORD:
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
        animal_data=dmanager.get_animal_data(),
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
        animal_data=dmanager.get_animal_data("user", user),
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
        animal_data=dmanager.get_animal_data("protocol_escaped", protocol),
        protocols=dmanager.protocols_and_subprotocols(),
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/animal_data/<animal_id>")
@login_required
def input(animal_id: str):
    """! Serves page to input experiment-data.

    @param animal_id  id of animal for which to add experiment-data.
    
    @return Rendered html experiment-data input page from jinja2-template.
    """
    animal_data = dmanager.get_animal_data("id", animal_id)
    # Redirect 
    if animal_data[0]["user"] != current_user.name:
        return redirect("/")
    notes = dmanager.get_notes(animal_id)
    general = General.query.get(animal_id)
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
        availible_anesthetic=PAnesthesia.query.filter(PAnesthesia.protocol == general.experiment),
        availible_analgesic=PAnalgesia.query.filter(PAnalgesia.protocol == general.experiment),
        availible_viruses=PVirus.query.filter(PVirus.protocol == general.experiment),
        animal_id=animal_id,
        animal_data=animal_data,
        protocols=dmanager.protocols_and_subprotocols(),
        notes=notes,
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/settings")
@login_required
def settings():
    return render_template(
        "settings.html", user_email=current_user.email, user_name=current_user.name
    )

@app.route("/settings/definitions", defaults={"category": ""})
@app.route("/settings/definitions/<category>")
@login_required
def availible(category: str):
    data = {}
    if category == "medication":
        data=AMedication.query.all()
    if category == "procedures":
        data=AProcedure.query.all()
    if category == "viruses":
        data=AVirus.query.all()
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

@app.route("/settings/protocols/<escaped_protocol>/<subprotocol>", defaults={"category": "general"})
@app.route("/settings/protocols/<escaped_protocol>/<subprotocol>/<category>")
@login_required
def subprotocol(escaped_protocol: str, subprotocol: str, category: str):
    protocol = Protocol.query.get(escaped_protocol)
    full_protocol = f"{escaped_protocol}/{subprotocol}"
    data = {}
    definitions = []
    if category == "anesthesia":
        data = PAnesthesia.query.filter(PAnesthesia.protocol == full_protocol)
        definitions = AMedication.query.all()    
    elif category == "analgesia":
        data = PAnalgesia.query.filter(PAnalgesia.protocol == full_protocol)
        definitions = AMedication.query.all()
    elif category == "procedures":
        data = PProcedure.query.filter(PProcedure.protocol == full_protocol)
        definitions = AProcedure.query.all()
    elif category == "viruses":
        data = PVirus.query.filter(PVirus.protocol == full_protocol)
        definitions = AVirus.query.all()
    elif category == "watercontrol":
        watercontrol = PWatercontrol.query.get(full_protocol)
        data = table_to_json(watercontrol) if watercontrol else {}

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

@app.route("/update/animal_data/subprotocol", methods=["POST"])
@login_required
def update_animal_subprotocol(): 
    """! Updates the subprotocol of an animal and initializes experiment-data.

    @param subprotocol  the new subprotocol

    @return error-/ success-message and status code.
    """
    subprotocol = request.form.get("subprotocol")
    animal_id = request.form.get("animal_id")
    txt, status = dmanager.set_subprotocol(animal_id, subprotocol) 
    return txt, status

@app.route("/update/animal_data/dates/<animal_id>", methods=["POST"])
@login_required
def update_dates(animal_id: str): 
    """! Updates the dates an animal 

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    print(f"Updateing dates: {animal_id}, {request.form['date']}")
    return dmanager.update_dates(animal_id, request.form["date"])

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

@app.route("/generate/weights/<animal_id>", methods=["POST"])
@login_required
def generate_weight_list(animal_id: str): 
    txt, status = dmanager.generate_weight_list(animal_id)
    return txt, status

@app.route("/store/<animal_id>", methods=["POST"])
@login_required
def store_experiment_data(animal_id: str):
    """! Adds new experiment-data from for given animal-id.

    @param animal_id  ID of animal for which to add data.
    @return error-/ success-message and status code.
    """
    data = json.loads(request.form.get("data"))
    try:
        dmanager.store_experiment_data(animal_id, data)
    except ParserException as ex:
        return ex.msg, ex.status
    return "Success", 200

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

@app.route("/clear/<animal_id>", methods=["POST"])
@login_required
def clear_experiment_data(animal_id: str):
    """! Adds new experiment-data from for given animal-id.

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    animal_data = dmanager.get_animal_data(animal_id)[0]
    dmanager.set_subprotocol(animal_id, animal_data["subprotocol"])
    return "Success", 200


@app.route("/generate/surgery_sheet/<animal_id>", methods=["POST"])
@login_required
def generate_surgery_sheet(animal_id: str):
    animal_data = dmanager.get_animal_data("id", animal_id)[0]
    if not date_filled(animal_data["death_date"]): 
        return "Animal is not yet sacrificed", 401
    dcreator = DCreator(
        template_path="templates/surgery_sheet", 
        protocol=dmanager.get_protocol(animal_id), 
        experiment_data=dmanager.load_protocal_data(animal_id),
        animal_data=animal_data,
        user_email=current_user.email
    )
    dcreator.create_from_template()
    return send_file("output/surgery_sheet.docx", as_attachment=True)

@app.route("/generate/score_sheet/<animal_id>", methods=["POST"])
@login_required
def generate_score_sheet(animal_id: str):
    animal_data = dmanager.get_animal_data("id", animal_id)[0]
    if not date_filled(animal_data["death_date"]): 
        return "Animal is not yet sacrificed", 401

    dcreator = DCreator(
        template_path="templates/score_sheet", 
        protocol=dmanager.get_protocol(animal_id), 
        experiment_data=dmanager.load_protocal_data(animal_id),
        animal_data=animal_data,
        user_email=current_user.email
    )
    dcreator.create_score_sheet()
    return send_file("output/score_sheet.docx", as_attachment=True)

@app.route("/settings/definitions/medication", methods=["POST"])
@login_required 
def update_medication_definitions():
    medication = AMedication.query.get(request.form["name"])
    if medication:
        medication.amount = request.form["amount"]
        medication.concentration = request.form["concentration"]
        medication.days_after_surgery = request.form["days_after_surgery"]
    else: 
        medication = AMedication(
            name=request.form["name"],
            amount=request.form["amount"],
            concentration=request.form["concentration"],
            days_after_surgery=request.form["days_after_surgery"]
        )
        db.session.add(medication)
    db.session.commit()
    return redirect("/settings/definitions/medication")

@app.route("/settings/definitions/procedure", methods=["POST"])
@login_required 
def update_procedure_definitions():
    procedure = AProcedure.query.get(request.form["name"])
    is_surgery = "surgery" in request.form
    if procedure:
        procedure.days_after_start = request.form["days_after_start"]
        procedure.duration = request.form["duration"]
        procedure.surgery = is_surgery
    else: 
        procedure = AProcedure(
            name=request.form["name"],
            days_after_start=request.form["days_after_start"],
            duration=request.form["duration"],
            surgery=is_surgery
        )
        db.session.add(procedure)
    db.session.commit()
    return redirect("/settings/definitions/procedures")

@app.route("/settings/definitions/virus", methods=["POST"])
@login_required 
def update_virus_definitions():
    virus = AVirus.query.get(request.form["name"])
    is_surgery = "surgery" in request.form
    if virus:
        print("updating existing virus enty: ", request.form)
        virus.days_after_start = request.form["days_after_start"]
        virus.amount = request.form["amount"]
    else: 
        print("adding new virus enty: ", request.form)
        virus = AVirus(
            name=request.form["name"],
            days_after_start=request.form["days_after_start"],
            amount=request.form["amount"],
        )
        db.session.add(virus)
    db.session.commit()
    return redirect("/settings/definitions/viruses")


@app.route("/definitions/delete/<category>/<name>", methods=["POST"])
@login_required 
def delete_definition(category, name): 
    name = html.unescape(name).replace("_", "/")
    elem_to_delete = None
    if category == "medication":
        elem_to_delete = AMedication.query.get(name)
    elif category == "procedures":
        elem_to_delete = AProcedure.query.get(name)
    elif category == "viruses":
        elem_to_delete = AVirus.query.get(name)
    if elem_to_delete is not None:
        db.session.delete(elem_to_delete)
    db.session.commit()
    return redirect("/settings/definitions/"+category)

@app.route("/settings/add_protocol", methods=["POST"]) 
@login_required 
def add_protocal():
    escaped_name = escape_protocol(request.form["name"])
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

@app.route("/settings/protocols/remove/<escaped_protocol>/<subprotocol>", methods=["POST"]) 
@login_required 
def remove_subprotocal(escaped_protocol, subprotocol):
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

@app.route("/settings/protocols/<protocol>/<subprotocol>/anesthesia", methods=["POST"])
@login_required 
def update_protocol_anesthesia(protocol, subprotocol):
    full_protocol = f"{protocol}/{subprotocol}"
    anesthesia = PAnesthesia.query.get((full_protocol, request.form["name"]))
    if anesthesia:
        anesthesia.amount = request.form["amount"]
        anesthesia.concentration = request.form["concentration"]
        anesthesia.days_after_surgery = request.form["days_after_surgery"]
    else: 
        anesthesia = PAnesthesia(
            protocol=full_protocol,
            name=request.form["name"],
            amount=request.form["amount"],
            concentration=request.form["concentration"],
            days_after_surgery=request.form["days_after_surgery"]
        )
        db.session.add(anesthesia)
    db.session.commit()
    return redirect(f"/settings/protocols/{protocol}/{subprotocol}/anesthesia")

@app.route("/settings/protocols/<protocol>/<subprotocol>/analgesia", methods=["POST"])
@login_required 
def update_protocol_analgesia(protocol, subprotocol):
    full_protocol = f"{protocol}/{subprotocol}"
    analgesia = PAnalgesia.query.get((full_protocol, request.form["name"]))
    if analgesia:
        analgesia.amount = request.form["amount"]
        analgesia.concentration = request.form["concentration"]
        analgesia.days_after_surgery = request.form["days_after_surgery"]
    else: 
        analgesia = PAnalgesia(
            protocol=full_protocol,
            name=request.form["name"],
            amount=request.form["amount"],
            concentration=request.form["concentration"],
            days_after_surgery=request.form["days_after_surgery"]
        )
        db.session.add(analgesia)
    db.session.commit()
    return redirect(f"/settings/protocols/{protocol}/{subprotocol}/analgesia")


@app.route("/settings/protocols/<protocol>/<subprotocol>/procedure", methods=["POST"])
@login_required 
def update_protocol_procedure(protocol, subprotocol):
    full_protocol = f"{protocol}/{subprotocol}"
    procedure = PProcedure.query.get((full_protocol, request.form["name"]))
    is_surgery = "surgery" in request.form
    if procedure:
        procedure.days_after_start = request.form["days_after_start"]
        procedure.duration = request.form["duration"]
        procedure.surgery = is_surgery
    else: 
        procedure = PProcedure(
            protocol=full_protocol,
            name=request.form["name"],
            days_after_start=request.form["days_after_start"],
            duration=request.form["duration"],
            surgery=is_surgery
        )
        db.session.add(procedure)
    db.session.commit()
    return redirect(f"/settings/protocols/{protocol}/{subprotocol}/procedures")

@app.route("/settings/protocols/<protocol>/<subprotocol>/virus", methods=["POST"])
@login_required 
def update_protocol_virus(protocol, subprotocol):
    full_protocol = f"{protocol}/{subprotocol}"
    virus = PVirus.query.get((full_protocol, request.form["name"]))
    is_surgery = "surgery" in request.form
    if virus:
        virus.days_after_start = request.form["days_after_start"]
        virus.amount = request.form["amount"]
    else: 
        virus = PVirus(
            protocol=full_protocol,
            name=request.form["name"],
            days_after_start=request.form["days_after_start"],
            amount=request.form["amount"],
        )
        db.session.add(virus)
    db.session.commit()
    return redirect(f"/settings/protocols/{protocol}/{subprotocol}/viruses")

@app.route("/settings/protocols/<protocol>/<subprotocol>/watercontrol", methods=["POST"])
@login_required 
def update_protocol_watercontrol(protocol, subprotocol):
    full_protocol = f"{protocol}/{subprotocol}"
    watercontrol = PWatercontrol.query.get(full_protocol)
    is_allowed = "allowed" in request.form
    if watercontrol:
        watercontrol.allowed = is_allowed
        watercontrol.days_after_start = request.form["days_after_start"]
        watercontrol.duration = request.form["duration"]
    else: 
        watercontrol = PWatercontrol(
            protocol=full_protocol,
            allowed=is_allowed,
            days_after_start=request.form["days_after_start"],
            duration=request.form["duration"],
        )
        db.session.add(watercontrol)
    db.session.commit()
    return redirect(f"/settings/protocols/{protocol}/{subprotocol}/watercontrol")

@app.route("/settings/protocols/<protocol>/<subprotocol>/delete/<category>/<name>", methods=["POST"])
@login_required 
def delete_protocol_entry(protocol, subprotocol, category, name): 
    print("Got category: ", category)
    full_protocol = f"{protocol}/{subprotocol}"
    name = html.unescape(name).replace("_", "/")
    elem_to_delete = None
    if category == "anesthesia":
        elem_to_delete = PAnesthesia.query.get((full_protocol, name))
    elif category == "analgesia":
        elem_to_delete = PAnalgesia.query.get((full_protocol, name))
    elif category == "procedures":
        elem_to_delete = PProcedure.query.get((full_protocol, name))
    elif category == "viruses":
        elem_to_delete = PVirus.query.get((full_protocol, name))
    if elem_to_delete is not None:
        db.session.delete(elem_to_delete)
    db.session.commit()
    return redirect(f"/settings/protocols/{protocol}/{subprotocol}/category")


if __name__=="__main__":
    app.run(debug=True)
