# flexible_parse

## Installation 

### Prerequisits 
`python3` and `pip3` should be installed on your computer or server. 

Also 

### Linux and MacOS


#### Using FLAKE locally or in a screen (recommended for private use)

Create virtual environment:
```
python3 -m venv .venv
```
This creates a virtual environment as a hidden folder named `.env`. (Read here
on why virtual environments might be helpful: https://pythonbasics.org/virtualenv/.
Now we need to enter the virtualenv: 
```
source .venv/bin/activate
```

Install requirements:
```
pip install -r requirements.txt
``` 

Start server: 
```
python3 src/app.py
```

#### Using FLAKE as systemd service (recommended on servers for "public" access)
Execute the steps above to run the server once and create all the passwords,
then: 

Set up the server.config
``` 
cp server.config.example server.config
``` 
You need not change any values. You may however change the PORT.

Set up the environment-file by first copying the template: 
```
cp example.env .env 
```
Then open the .env file with you favorite text-editor and fill the master password: 
```
FLAKE_MASTER_PASSWORD=<your-secret-master-password>
```

Then run `sudo make install` to initialize the server 

(When updating simply run `sudo make update` to update to the newst version. **`make 
install` will always overwrite the database and the config!**)

Finally start the server by running: 
```
sudo systemctl flake.service 
```

## Install Latex for 


## Database migrations with Alembic

Alembic updates an existing database when the SQLAlchemy models or stored data
need to change. By default it operates on `instance/larkum.db`; set
`FLAKE_DATABASE_URL` to target a different database.

Before applying migrations, stop the application and create a database backup.
Then inspect the current and pending revisions and upgrade to the latest one:

```sh
alembic current
alembic history
alembic upgrade head
```

When changing the database schema, update the models first and generate a new
revision:

```sh
alembic revision --autogenerate -m "short description"
```

Always review the generated file in `alembic/versions/`. Autogeneration detects
schema changes, but data cleanup or transformation must be written manually in
`upgrade()`. Test the migration against a database copy before committing the
model and revision together. Do not use `alembic stamp` unless intentionally
baselining a database, because it records revisions without running them.

The type decisions for issue #3 and the scope of its migration are documented in
[docs/database-types.md](docs/database-types.md).

## Development checks

Install the development dependencies in the virtual environment, then run the
type checker and tests from the repository root:

```sh
pip install -r requirements-dev.txt
pyright
PYTHONPATH=src python -m unittest discover -s tests
```

JavaScript checks run without additional dependencies:

```sh
node tests/test_experiment_copy.js
node tests/test_request_errors.js
node tests/test_message_rendering.js
```

To check the copy/paste workflow in headless Chromium, start
`chromedriver --port=9516`, then run:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tests/browser_experiment_copy.py
```

The browser check uses an isolated in-memory database and saves its review
screenshot to `/tmp/flake-copy-paste-review.png`.

## Copy experiment data

On the main, user, or protocol overview, choose **Copy** mode and select one
source animal. Click **Copy from selected animal** and choose procedures,
medication, and/or viruses. The overview then switches to **Paste** mode and
clears the source selection so you can select destination animals. You can
switch back to Copy mode to choose another source.

Click **Paste to selected animals** to review the destinations. Green rows have
both start and sacrifice dates. For red rows, enter missing dates directly or
use the corresponding source dates. **Skip animal** excludes the entire animal
from the operation, including date changes. Existing dates are preserved, and
each included destination needs an assigned protocol and subprotocol.

Pasting replaces every entry in the selected categories using the source's
latest data. Procedure dates can keep their calendar dates or shift relative
to each destination's start date; sacrifice procedures always use the
destination's sacrifice date. Medication amounts are recalculated when their
dates or inputs change. Existing weights and notes are retained. All included
animals are validated before writing, and dates and copied rows are saved in
one transaction.
