"""Order choices and selection checks shared by the form and submission logic."""
from werkzeug.exceptions import Forbidden

from data_manager.tables import PAllowedMice, PGeneral, Protocol, User, db
from data_manager.types import OrderLicenceOption, OrderLineOption
from exceptions.exceptions import EntryNotFound, InvalidTypeException


def _user_is_allowed(user: User, general: PGeneral) -> bool:
    # These entries are PyRAT usernames, not account email addresses. Both the
    # settings UI and older imports can write comma lists with varying spacing.
    username = (user.name or "").strip()
    allowed_users = {name.strip() for name in (general.allowed_users or "").split(",")}
    return bool(username) and username in allowed_users


def get_order_licences(user: User) -> list[OrderLicenceOption]:
    """Return the user's existing protocol/subprotocol pairs in display order."""
    allowed_licences = {
        general.protocol for general in PGeneral.query.all() if _user_is_allowed(user, general)
    }
    choices: list[OrderLicenceOption] = []
    if not allowed_licences:
        return choices
    for protocol in Protocol.query.all():
        for subprotocol in protocol.get_subprotocols():
            licence = f"{protocol.escaped}/{subprotocol}"
            if licence in allowed_licences:
                choices.append({
                    "licence": licence, "protocol": protocol.name, "subprotocol": subprotocol,
                })
    return sorted(choices, key=lambda choice: (
        choice["protocol"].casefold(), choice["subprotocol"].casefold(), choice["licence"],
    ))


def _require_order_licence(user: User, licence: str) -> None:
    if not isinstance(licence, str):
        raise InvalidTypeException("Select a protocol and subprotocol for the order.")
    escaped_protocol, separator, subprotocol = licence.partition("/")
    if not separator or not escaped_protocol or not subprotocol or "/" in subprotocol:
        raise InvalidTypeException("Select a protocol and subprotocol for the order.")
    protocol = db.session.get(Protocol, escaped_protocol)
    if protocol is None or subprotocol not in protocol.get_subprotocols():
        raise EntryNotFound("The selected order licence no longer exists.")
    general = PGeneral.query.filter_by(protocol=licence).first()
    if general is None or not _user_is_allowed(user, general):
        raise Forbidden("You are not allowed to order animals for this licence.")


def get_order_lines(user: User, licence: str) -> list[OrderLineOption]:
    """Return configured lines for an allowed licence, retaining zero/NULL limits.

    A configured line is a row in PAllowedMice; global line definitions and
    imported animal records do not grant permission to order that line. Quota
    checks belong to submission validation, so an unset allowance is returned
    as None rather than interpreted as zero or unlimited.
    """
    _require_order_licence(user, licence)
    return [
        {"line": line.name, "allowance": line.num_availible_animals}
        for line in PAllowedMice.query.filter_by(protocol=licence).order_by(PAllowedMice.name).all()
    ]


def validate_order_selection(user: User, licence: str, line: str) -> PAllowedMice:
    """Recheck access and return the current allowance for a submitted selection.

    Call this again on submission even if the form previously obtained valid
    choices: access, licences and line configurations can change in between.
    This validates eligibility only; it does not check the requested quantity.
    """
    _require_order_licence(user, licence)
    if not isinstance(line, str) or not line.strip():
        raise InvalidTypeException("Select a line for the order.")
    allowance = PAllowedMice.query.filter_by(protocol=licence, name=line).first()
    if allowance is None:
        raise EntryNotFound("The selected line is not configured for this licence.")
    return allowance
