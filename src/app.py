import json
from flask import Flask, render_template, request
from data_manager.dmanager import DManager

dmanager = DManager("data/")
app = Flask(__name__)

@app.route("/")
def main():
    return render_template("index.html", users=dmanager.users)

@app.route("/upload/pyrat_csv", methods=["POST"])
def upload_pyrat_data():
    content = request.files
    # Create path for this user to avoid overwriting when muliple users perform action.
    user = json.loads(request.form.get("user"))["name"] 
    tmp_path = user + ".csv"
    # upload via data-manager
    dmanager.upload_csv(tmp_path, content.get("csv"))
    return "successfully updloaded pyrat-data", 200

@app.route("/<user>")
def overview(user):
    return render_template(
        "overview.html", user=user, animal_data=dmanager.animal_data
    )

@app.route("/<user>/<mouse_id>")
def input(user: str, mouse_id: str):
    return render_template("input.html")

if __name__=="__main__":
    dmanager.load_data()
    app.run(debug=True)
