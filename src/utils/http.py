"""Responses for messages that must be displayed as literal text."""
from flask import Response


def text_response(message: str = "", status: int = 200) -> Response:
    return Response(message, status=status, content_type="text/plain; charset=utf-8")
