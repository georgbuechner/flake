import bcrypt
from typing import Dict, List
from data_manager.tables import table_to_json
from os.path import exists as file_exists
from typing import Tuple

def sort_query(obj_list, key: str):
    """! Sorts a given list of objects by given key. 

    @param obj_list  List of objects to sort.
    @param key  Key by which to stort list.

    @return Sorted list.
    """
    def sort_by_key(e):
        if "date" in key:
            return table_to_json(e)[key]
        return int(table_to_json(e)[key])
    print("OBJ_LIST: ", type(obj_list))
    if not isinstance(obj_list, list):
        if obj_list.first():
            obj_list = [x for x in obj_list]
        else:
            return []
    obj_list.sort(key=sort_by_key)
    return obj_list


def hash_pw(password: str, salt: str = None) -> str: 
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

