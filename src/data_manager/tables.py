from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    """!An admin user capable of viewing reports.

    @param email  Email address of user
    @param name  Name of user 
    @param password  Hashed password of user 
    @param sal  Salt matching password-hash.
    @param password  Encrypted password for the user

    """
    __tablename__ = 'user'

    email = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, primary_key=False)
    password = db.Column(db.String, primary_key=False)
    salt = db.Column(db.String, primary_key=False)
    authenticated = db.Column(db.Boolean, default=False)

    def is_active(self):
        """! True, as all users are active."""
        return True

    def get_id(self):
        """! Return the email address to satisfy Flask-Login's requirements."""
        return self.email

    def is_authenticated(self):
        """! Return True if the user is authenticated."""
        return self.authenticated

    def is_anonymous(self):
        """! False, as anonymous users aren't supported."""
        return False

class AMedication(db.Model): 
    __tablename__ = "availible_medication"

    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

class AProcedure(db.Model): 
    __tablename__ = "availible_procedures"

    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)
    surgery = db.Column(db.Boolean, primary_key=False)

class AVirus(db.Model): 
    __tablename__ = "availible_viruses"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

class PMedication(db.Model): 
    __tablename__ = "protocol_medication"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    amount = db.Column(db.String, primary_key=False)
    concentration = db.Column(db.String, primary_key=False)
    days_after_surgery = db.Column(db.String, primary_key=False)

class PProcedure(db.Model): 
    __tablename__ = "protocol_procedures"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    duration = db.Column(db.String, primary_key=False)
    surgery = db.Column(db.Boolean, primary_key=False)

class PVirus(db.Model): 
    __tablename__ = "protocol_viruses"

    protocol = db.Column(db.String, primary_key=True) 
    name = db.Column(db.String, primary_key=True) 
    days_after_start = db.Column(db.String, primary_key=False)
    amount = db.Column(db.String, primary_key=False)

class Protocol(db.Model): 
    __tablename__ = "protocols"

    name = db.Column(db.String, primary_key=False) 
    escaped = db.Column(db.String, primary_key=True)
    subprotocols = db.Column(db.String, primary_key=False)

    def get_subprotocols(self):
        subprotocols = self.subprotocols.split(";")
        if len(subprotocols) > 0 and subprotocols[0] == "":
            return []
        return subprotocols

    def add_subprotocol(self, subprotocol):
        if len(self.subprotocols) == 0:
            self.subprotocols += subprotocol 
        else:
            self.subprotocols += ";" + subprotocol

    def remove_subprotocol(self, subprotocol):
        subprotocols = self.get_subprotocols() 
        subprotocols.remove(subprotocol)
        self.subprotocols = ";".join(subprotocols)
