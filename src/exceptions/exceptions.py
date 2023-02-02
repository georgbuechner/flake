class ParserException(Exception):
    """! Base class for all exception """
    def __init__(self, msg: str, status: int):
        """! initiales exception 

        @param msg  Message passed to the user
        @param status  Http status code 
        """
        self.msg = msg 
        self.status = status

class EntryNotFound(ParserException):
    def __init__(self, msg: str, status: int):
        super(EntryNotFound, self).__init__(msg, status)

class QueryEmpty(ParserException):
    def __init__(self, msg: str, status: int):
        super(ParserException, self).__init__(msg, status)
