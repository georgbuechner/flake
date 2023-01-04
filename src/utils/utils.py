import bcrypt
from typing import Dict, List
from data_manager.tables import table_to_json

def sort(obj_list: List[Dict[str, any]], key: str):
    """! Sorts a given list of objects by given key. 

    @param obj_list  List of objects to sort.
    @param key  Key by which to stort list.

    @return Sorted list.
    """
    def sort_by_key(e):
        return e[key]
    obj_list.sort(key=sort_by_key)
    return obj_list

def sort_query(obj_list, key: str):
    """! Sorts a given list of objects by given key. 

    @param obj_list  List of objects to sort.
    @param key  Key by which to stort list.

    @return Sorted list.
    """
    if obj_list.first():
        obj_list = [table_to_json(x) for x in obj_list]
        def sort_by_key(e):
            return e[key]
        obj_list.sort(key=sort_by_key)
        return obj_list
    return []


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
