"""Responses for messages that must be displayed as literal text."""
from flask import Response


def text_response(message="", status=200):
    return Response(message, status=status, content_type="text/plain; charset=utf-8")
