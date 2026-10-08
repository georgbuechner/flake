class FlakeError(Exception):
    """! Base class for all exception """
    def __init__(self, msg: str, status: int):
        """! initiales exception 

        @param msg  Message passed to the user
        @param status  Http status code 
        """
        self.msg = msg 
        self.status = status
        super().__init__(msg)

class EntryNotFound(FlakeError):
    def __init__(self, msg: str, status: int = 404):
        super().__init__(msg, status)

class QueryEmpty(FlakeError):
    def __init__(self, msg: str, status: int):
        super().__init__(msg, status)

class DublicateEntry(FlakeError):
    def __init__(self, msg: str):
        super().__init__(msg, 409)

class InvalidTypeException(FlakeError): 
    def __init__(self, msg: str):
        super().__init__(msg, 400)

class InvalidNameException(FlakeError): 
    def __init__(self, name: str, msg: str):
        self.msg = f"Invalid name: <i>{name}</i>. {msg}"
        self.status = 406
        super().__init__(self.msg, self.status)

class MissingEntryException(FlakeError):
    def __init__(self, entry: str, msg: str = None):
        self.msg = "Missing entry: "
        if msg != None:
            self.msg = msg
        self.msg += f"<i>{entry}</i>!"
        self.status = 406
        super().__init__(self.msg, self.status)

class AnimalDataIncompleteException(FlakeError):
    def __init__(self):
        self.msg = "Animal Data incomplete. Can't generate p9"
        self.status = 409
        super().__init__(self.msg, self.status)

class ParseException(FlakeError): 
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(self.msg, 400)

class InvalidDateException(FlakeError): 
    def __init__(self, date_str: str, formats: str):
        self.msg = (
            f"The date \"{date_str}\" did not match any of the following"
            + f"formats: \"<i>{formats}</i>\""
        )
        super().__init__(self.msg, 400)

class ConfirmationRequired(FlakeError): 
    def __init__(self, msg: str, status: int = 409):
        super().__init__(msg, status)

class AnimalNotSacrificed(FlakeError):
    def __init__(self):
        super().__init__("Animal is not yet sacrificed", 409)

class WeightGenerationUnavailable(FlakeError):
    def __init__(self, msg: str, status: int = 409):
        super().__init__(msg, status)
