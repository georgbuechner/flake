import json
from flask import Flask, render_template, request, send_file
from data_manager.dmanager import DManager
from data_manager.sql_connector import SqlConnector
from document_creator.dcreator import DCreator

# Create global instance of sql-connector, data-manager and flask-app.
sql_connector = SqlConnector("data/database.db", "resources/tables.json")
dmanager = DManager(sql_connector)
app = Flask(__name__)

@app.route("/")
def main():
    """! Serves main-page showing all users, protocols. 

    @return Rendered html main-page from jinja2-template.
    """
    return render_template(
        "index.html", users=dmanager.users(), protocols=dmanager.protocols
    )

@app.route("/overview")
def overview():
    """! Serves general overview of all animal-data. 

    @return Rendered html overview-page from jinja2-template.
    """
    protocols = dmanager.protocols
    return render_template(
        "overview.html", 
        animal_data=dmanager.get_animal_data(),
        protocols=dmanager.protocols
    )

@app.route("/users/<user>")
def user_overview(user: str):
    """! Serves overview of all animal-data of a single user 

    @param user  the user for which to show animal-data.

    @return Rendered html user-overview page from jinja2-template.
    """
    return render_template(
        "user_overview.html", 
        user=user, 
        animal_data=dmanager.get_animal_data("user", user),
        protocols=dmanager.protocols
    )

@app.route("/protocols/<protocol>")
def protocol_overview(protocol: str):
    """! Serves overview of all animal-data of a single protocol.

    @param protocol  the protocol for which to show animal-data.

    @return Rendered html protocol-overview page from jinja2-template.
    """
    return render_template(
        "protocol_overview.html", 
        protocol=protocol,
        animal_data=dmanager.get_animal_data("protocol_escaped", protocol),
        protocols=dmanager.protocols
    )

@app.route("/animal_data/<animal_id>")
def input(animal_id: str):
    """! Serves page to input experiment-data.

    @param animal_id  id of animal for which to add experiment-data.
    
    @return Rendered html experiment-data input page from jinja2-template.
    """
    experiment_data = dmanager.load_protocal_data(animal_id)
    return render_template(
        "input.html", 
        stored=experiment_data.stored,
        general=experiment_data.general,
        anesthesia=experiment_data.anesthetic, 
        availible_anesthetic=experiment_data.availible_anesthetic,
        availible_analgesic=experiment_data.availible_analgesic,
        analgesic=experiment_data.analgesic,
        procedures=experiment_data.procedures,
        post_procedures=experiment_data.post_procedures,
        surgery_start=experiment_data.surgery_start,
        animal_id=animal_id,
        animal_data=dmanager.get_animal_data("id", animal_id),
        protocols=dmanager.protocols
    )

@app.route("/update/animal_data/subprotocol", methods=["POST"])
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
def store_animal_data():
    """! Adds new animal-data from .CSV.

    @return error-/ success-message and status code.
    """
    content = request.files
    # upload via data-manager
    txt, status = dmanager.extract_animal_data(content.get("csv"))
    return txt, status

@app.route("/store/<animal_id>", methods=["POST"])
def store_experiment_data(animal_id: str):
    """! Adds new experiment-data from for given animal-id.

    @param animal_id  ID of animal for which to add data.
    @return error-/ success-message and status code.
    """
    data = json.loads(request.form.get("data"))
    dmanager.store_experiment_data(animal_id, data)
    return "Success", 200

@app.route("/clear/<animal_id>", methods=["POST"])
def clear_experiment_data(animal_id: str):
    """! Adds new experiment-data from for given animal-id.

    @param animal_id  ID of animal for which to add data.

    @return error-/ success-message and status code.
    """
    dmanager.clear_experiment_data(animal_id)
    return "Success", 200

@app.route("/generate/surgery_sheet/<protocol>/<animal_id>", methods=["POST"])
def generate_surgery_sheet(protocol: str, animal_id: str):
    dcreator = DCreator(
        template_path="templates/surgery_sheet", 
        protocol=protocol, 
        experiment_data=dmanager.load_protocal_data(animal_id),
        animal_data=dmanager.get_animal_data("id", animal_id)[0]
    )
    dcreator.create_from_template()
    return send_file("output/output.docx", as_attachment=True)


if __name__=="__main__":
    app.run(debug=True)
