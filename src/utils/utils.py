import bcrypt
from typing import Dict, List

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

def hash_pw(password: str) -> str: 
    # Adding the salt to password
    salt = bcrypt.gensalt()
    # Hashing the password
    return bcrypt.hashpw(password.encode("utf-8"), salt)

