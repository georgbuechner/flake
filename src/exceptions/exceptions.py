class ParserException(Exception):
    """! Base class for all exception """
    def __init__(self, msg: str, status: int):
        """! initiales exception 

        @param msg  Message passed to the user
        @param status  Http status code 
        """
        self.msg = msg 
        self.status = status
