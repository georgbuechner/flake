import json
from flask import Flask, render_template, request, send_file, redirect
from flask_login import LoginManager, login_required, login_user, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from data_manager.dmanager import DManager
from data_manager.sql_connector import SqlConnector
from document_creator.dcreator import DCreator
from exceptions.exceptions import ParserException
from users.user import User, db
from utils.utils import hash_pw

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
    return render_template(
        "index.html", users=dmanager.users(), 
        protocols=dmanager.protocols,
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
    protocols = dmanager.protocols
    return render_template(
        "overview.html", 
        animal_data=dmanager.get_animal_data(),
        protocols=dmanager.protocols,
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
        protocols=dmanager.protocols,
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
        protocols=dmanager.protocols,
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
    experiment_data = dmanager.load_protocal_data(animal_id)
    notes = dmanager.get_notes(animal_id)
    return render_template(
        "input.html", 
        stored=experiment_data.stored,
        general=experiment_data.general,
        viruses=experiment_data.viruses,
        anesthesia=experiment_data.anesthetic, 
        availible_anesthetic=experiment_data.availible_anesthetic,
        availible_analgesic=experiment_data.availible_analgesic,
        availible_viruses=experiment_data.availible_viruses,
        analgesic=experiment_data.analgesic,
        procedures=experiment_data.procedures,
        post_procedures=experiment_data.post_procedures,
        surgery_start=experiment_data.surgery_start,
        animal_id=animal_id,
        animal_data=dmanager.get_animal_data("id", animal_id),
        protocols=dmanager.protocols,
        notes=notes,
        user_email=current_user.email,
        user_name=current_user.name
    )

@app.route("/update/animal_data/subprotocol", methods=["POST"])
@login_required
def update_animal_subprotocol(): 
    """! Updates the subprotocol of an animal 

    @param subprotocol  the new subprotocol

    @return error-/ success-message and status code.
    """
    subprotocol = request.form.get("subprotocol")
    animal_id = request.form.get("animal_id")
    txt, status = dmanager.update_animal_field(animal_id, "subprotocol", subprotocol) 
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
    dmanager.clear_experiment_data(animal_id)
    return "Success", 200

@app.route("/generate/surgery_sheet/<animal_id>", methods=["POST"])
@login_required
def generate_surgery_sheet(animal_id: str):
    dcreator = DCreator(
        template_path="templates/surgery_sheet", 
        protocol=dmanager.get_protocol(animal_id), 
        experiment_data=dmanager.load_protocal_data(animal_id),
        animal_data=dmanager.get_animal_data("id", animal_id)[0]
    )
    dcreator.create_from_template()
    return send_file("output/surgery_sheet.docx", as_attachment=True)

@app.route("/generate/score_sheet/<animal_id>", methods=["POST"])
@login_required
def generate_score_sheet(animal_id: str):
    dcreator = DCreator(
        template_path="templates/score_sheet", 
        protocol=dmanager.get_protocol(animal_id), 
        experiment_data=dmanager.load_protocal_data(animal_id),
        animal_data=dmanager.get_animal_data("id", animal_id)[0]
    )
    dcreator.create_score_sheet()
    return send_file("output/score_sheet.docx", as_attachment=True)


if __name__=="__main__":
    app.run(debug=True)
