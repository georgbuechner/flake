from flask import Flask, render_template
import clevercsv 
import os
import json

USER_DIR = "user_files/"
DATA = []
USERS = []

app = Flask(__name__)

@app.route("/")
def main():
    return render_template("index.html", users=USERS)

@app.route("/<user>")
def overview(user):
    print("LIST FIELDS: ", DATA)
    return render_template("overview.html", user=user, list_fields=DATA)

@app.route("/<user>/<mouse_id>")
def input(user, mouse_id):
    return render_template("input.html")

def load_data():
    with open("resources/mapping.json") as f:
        mapping = json.load(f)
    list_fields = []
    users = set()  # using set to avod dublicate
    for filename in os.listdir(USER_DIR):
        full_path = os.path.join(USER_DIR, filename)
        fields = {}
        print("PATH: ", full_path)
        if os.path.isfile(full_path):
            df = clevercsv.read_dataframe(full_path)
            print("DATA: ", df)
            for key in df.keys():
                value = df[key].values[0]
                if key in mapping:
                    fields[mapping[key]] = value
            print("FIELDS: ", fields)
            list_fields.append(fields)
            users.add(fields["user"])
    return list_fields, users

if __name__=="__main__":
    DATA, USERS = load_data()
    app.run(debug=True)
