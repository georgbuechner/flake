class ParserException(Exception):
    """! Base class for all exception """
    def __init__(self, msg: str, status: int):
        """! initiales exception 

        @param msg  Message passed to the user
        @param status  Http status code 
        """
        self.msg = msg 
        self.status = status
        super().__init__(msg)

class EntryNotFound(ParserException):
    def __init__(self, msg: str, status: int):
        super().__init__(msg, status)

class QueryEmpty(ParserException):
    def __init__(self, msg: str, status: int):
        super().__init__(msg, status)

class DublicateEntry(ParserException):
    def __init__(self, msg: str):
        super().__init__(msg, 409)

class InvalidTypeException(ParserException): 
    def __init__(self, msg: str):
        super().__init__(msg, 400)

class MissingEntryException(ParserException):
    def __init__(self, entry: str, msg: str = None):
        self.msg = "Missing entry: "
        if msg != None:
            self.msg = msg
        self.msg += f"<i>{entry}</i>!"
        self.status = 406
        super().__init__(self.msg, self.status)
