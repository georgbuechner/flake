"""Consistent error responses for page requests and AJAX operations."""
from flask import current_app, make_response, render_template, request
from werkzeug.exceptions import HTTPException

from data_manager.tables import db
from exceptions.exceptions import FlakeError


def is_ajax_request():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def handle_request_error(error):
    db.session.rollback()
    if isinstance(error, FlakeError):
        message, status = error.msg, error.status
        response = make_response("", status)
    elif isinstance(error, HTTPException):
        message, status = error.description, error.code
        response = error.get_response()
    else:
        current_app.logger.exception("Unexpected error handling %s", request.path)
        message = (
            "Sorry, an unexpected error occurred. "
            "The error has been logged. Contact the system administration."
        )
        status = 500
        response = make_response("", status)

    wants_html = (
        not is_ajax_request()
        and request.accept_mimetypes["text/html"] > request.accept_mimetypes["text/plain"]
    )
    if wants_html:
        response.set_data(render_template("error.html", message=message, status=status))
        response.content_type = "text/html; charset=utf-8"
    else:
        response.set_data(message)
        response.content_type = "text/plain; charset=utf-8"
    return response


def register_error_handlers(app):
    for error_type in (FlakeError, HTTPException, Exception):
        app.register_error_handler(error_type, handle_request_error)
