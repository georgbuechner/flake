# flexible_parse

## Installation 

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
