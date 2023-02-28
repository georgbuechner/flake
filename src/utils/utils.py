import base64
import bcrypt
import json
import os
import getpass
from typing import Dict, List
from data_manager.tables import table_to_json
from os.path import exists as file_exists
from typing import Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def sort_query(obj_list, key: str, to_int: bool = False):
    """! Sorts a given list of objects by given key. 

    @param obj_list  List of objects to sort.
    @param key  Key by which to stort list.

    @return Sorted list.
    """
    def sort_by_key(e):
        try:
            if to_int:
                return int(table_to_json(e)[key])
            else:
                return table_to_json(e)[key]
        except Exception as err:
            print(f"sort_query: key: {key}, value: {table_to_json(e)[key]} failed: {repr(err)}") 
            return 0
    if not isinstance(obj_list, list):
        if obj_list.first():
            obj_list = [x for x in obj_list]
        else:
            return []
    obj_list.sort(key=sort_by_key)
    return obj_list


def hash_pw(password: str, salt: str = None) -> Tuple[str, str]: 
    """! Creates hash from given password with salt and retuns hash and salt 

    @param password  The password to be hashed 
    @param salt  The salt. If not given, generates new salt. 
    @return password and salt (this should be stored when creating hash for the
    first time!)
    """
    # Adding the salt to password
    if salt is None:
        salt = bcrypt.gensalt()
    # Hashing the password
    return bcrypt.hashpw(password.encode("utf-8"), salt), salt

def has_signature(username: str) -> bool:
    sig_path = f"src/signatures/{escape(username)}"
    return file_exists(f"{sig_path}.png") or file_exists(f"{sig_path}.jpg")

def get_signature_path(username: str) -> Tuple[str, str]: 
    """ Checks src/signatures directory for signitures by given user and gets 
    signature-path and mimetype.

    Returns only `signitures/<filename>` to be flask compatible. For accessing
    file, add `src`: `f"src/{path}"`.
    """
    sig_path = f"signatures/{escape(username)}"
    if file_exists(f"src/{sig_path}.png"): 
        return f"{sig_path}.png", "image/png"
    elif file_exists(f"src/{sig_path}.jpg"): 
        return f"{sig_path}.jpg", "image/jpeg"
    return None, None

def escape(string: str) -> str: 
    """! Escape string to be url compatible. 

    Removes whitespaces (" ") and replaces slashs ("/") underscore ("_").
    
    @param string String to escape.
    @return Escaped string.
    """
    return string.replace(" ", "").replace("/", "_")

def get_keys_from_config(path: str) -> Tuple[str, str]: 
    with open(path) as f:
        config = json.load(f)

    def encode_password(pw: str, salt=None):
        if salt is None:
            salt = bcrypt.gensalt() # os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(pw)), salt

    secret = config["secret"]
    lab_password = config["lab_password"]
    if secret != "":
        password = config["password"]["password"].encode()
        salt = config["password"]["salt"].encode()
        inp = getpass.getpass("password: ") 
        if hash_pw(inp, salt)[0] == password:
            encoded_password, _ = encode_password(inp.encode(), salt)
            fernet = Fernet(encoded_password) 
            return fernet.decrypt(secret).decode(), fernet.decrypt(lab_password).decode()
        else: 
            exit("wrong password") 
    else: 
        secret = getpass.getpass("Secret: ")
        lab_password = getpass.getpass("lab password (used for registration): ")
        password = getpass.getpass("password (for decrypting config): ")
        r_password = getpass.getpass("retype password: ")
        if password != r_password: 
            exit("Passwords do not match!") 
        # Store password
        encoded_password, salt = encode_password(password.encode())
        hashed_password, _ = hash_pw(password, salt)
        config["password"]["password"] = hashed_password.decode("utf-8")
        config["password"]["salt"] = salt.decode("utf-8")
        # Encrypt secret and lab-password
        fernet = Fernet(encoded_password)
        csecret = fernet.encrypt(secret.encode())
        clab_password = fernet.encrypt(lab_password.encode())
        config["secret"] = csecret.decode("utf-8")
        config["lab_password"] = clab_password.decode("utf-8")
        # Store updated config
        with open(path, "w") as f:
            json.dump(config, f)
        return secret, lab_password

def get_root_user(path):
    # Load config
    with open(path) as f:
        config = json.load(f)
    # Check if root already exists
    if "root-mail" in config: 
        return config["root-mail"]
    # Get name from input, store to config and return
    root_email = input("Root email: ")
    config["root-mail"] = root_email
    with open(path, "w") as f:
        json.dump(config, f)
    return root_email
