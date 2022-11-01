import json
from flask import Flask, render_template, request
from data_manager.dmanager import DManager
from data_manager.sql_connector import SqlConnector


sql_connector = SqlConnector("data/database.db", "resources/tables.json")
dmanager = DManager("data/animal_data/", sql_connector)
app = Flask(__name__)

@app.route("/")
def main():
    return render_template(
        "index.html", users=dmanager.users, protocols=dmanager.protocols
    )

@app.route("/overview")
def overview():
    return render_template(
        "overview.html", animal_data=dmanager.get_animal_data()
    )

@app.route("/users/<user>")
def users(user):
    return render_template(
        "user_overview.html", 
        user=user, 
        animal_data=dmanager.get_animal_data("user", user)
    )

@app.route("/protocols/<protocol>")
def protocols(protocol):
    return render_template(
        "protocol_overview.html", 
        protocol=protocol,
        animal_data=dmanager.get_animal_data("protocol_escaped", protocol)
    )

@app.route("/animal_data/<animal_id>")
def input(animal_id: str):
    experiment_data = dmanager.load_protocal_data(animal_id)
    print("analgesic:", experiment_data.analgesic)
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
        animal_data=dmanager.get_animal_data("id", animal_id)
    )

@app.route("/store/<animal_id>", methods=["POST"])
def store_data(animal_id: str):
    data = json.loads(request.form.get("data"))
    dmanager.store(animal_id, data)
    return "Success", 200

@app.route("/upload/pyrat_csv", methods=["POST"])
def upload_pyrat_data():
    content = request.files
    # Create path for this user to avoid overwriting when muliple users perform action.
    user = json.loads(request.form.get("user"))["name"] 
    tmp_path = user + ".csv"
    # upload via data-manager
    status = dmanager.upload_csv(tmp_path, content.get("csv"))
    if status == 200:
        return "successfully updloaded pyrat-data", status
    elif status == 409:
        return "Couldn't updload pyrat-data: animal exists", status


if __name__=="__main__":
    dmanager.load_data()
    app.run(debug=True)
