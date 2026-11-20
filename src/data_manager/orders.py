"""Order choices and validation shared by the form and submission logic."""
from datetime import date as Date, timedelta
import re
from typing import Any, Mapping

from sqlalchemy.orm import Query
from werkzeug.exceptions import Forbidden

from data_manager.animal_counts import get_animal_counts
from data_manager.tables import (
    AnimalOrder, AnimalOrderByData, AnimalOrderById, PAllowedMice, PGeneral, Protocol,
    User, db, optional_integer,
)
from data_manager.types import OrderLicenceOption, OrderLineOption
from exceptions.exceptions import (
    EntryNotFound, InvalidDateException, InvalidTypeException, OrderAlreadyReviewed,
    OrderAllowanceNotConfigured, OrderQuotaExceeded,
)
from utils.dt_utils import today


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


def _require_existing_order_licence(licence: str) -> None:
    if not isinstance(licence, str):
        raise InvalidTypeException("Select a protocol and subprotocol for the order.")
    escaped_protocol, separator, subprotocol = licence.partition("/")
    if not separator or not escaped_protocol or not subprotocol or "/" in subprotocol:
        raise InvalidTypeException("Select a protocol and subprotocol for the order.")
    protocol = db.session.get(Protocol, escaped_protocol)
    if protocol is None or subprotocol not in protocol.get_subprotocols():
        raise EntryNotFound("The selected order licence no longer exists.")


def _require_order_licence(user: User, licence: str) -> None:
    _require_existing_order_licence(licence)
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
    counts = get_animal_counts(*licence.split("/", 1))
    choices: list[OrderLineOption] = []
    for line in PAllowedMice.query.filter_by(protocol=licence).order_by(PAllowedMice.name).all():
        used = counts.get(line.name, 0)
        allowance = line.num_availible_animals
        choices.append({
            "line": line.name, "allowance": allowance, "used": used,
            "remaining": None if allowance is None else max(0, allowance - used),
        })
    return choices


def validate_order_selection(user: User, licence: str, line: str) -> PAllowedMice:
    """Recheck access and return the current allowance for a submitted selection.

    Call this again on submission even if the form previously obtained valid
    choices: access, licences and line configurations can change in between.
    This validates eligibility only; it does not check the requested quantity.
    """
    _require_order_licence(user, licence)
    return _get_order_allowance(licence, line)


def _get_order_allowance(licence: str, line: str) -> PAllowedMice:
    if not isinstance(line, str) or not line.strip():
        raise InvalidTypeException("Select a line for the order.")
    allowance = PAllowedMice.query.filter_by(protocol=licence, name=line).first()
    if allowance is None:
        raise EntryNotFound("The selected line is not configured for this licence.")
    return allowance


def minimum_order_delivery_date() -> Date:
    return today().date() + timedelta(days=3)


def _delivery_date(value: object) -> Date:
    if type(value) is Date:
        delivery = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            delivery = Date.fromisoformat(text)
        except ValueError as error:
            raise InvalidDateException(text, "YYYY-MM-DD") from error
        if delivery.isoformat() != text:
            raise InvalidDateException(text, "YYYY-MM-DD")
    else:
        raise InvalidDateException(str(value), "YYYY-MM-DD")
    minimum = minimum_order_delivery_date()
    if delivery < minimum:
        raise InvalidTypeException(
            f"Delivery must be on or after {minimum.isoformat()} (three calendar days from today)."
        )
    return delivery


def _required_integer(value: object, field: str, minimum: int) -> int:
    number = optional_integer(value, field, non_negative=True)
    if number is None or number < minimum:
        raise InvalidTypeException(f"Order {field} must be an integer of at least {minimum}.")
    return number


def _has_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None and value != []


def _order_from_submission(user: User, data: Mapping[str, Any]) -> AnimalOrderById | AnimalOrderByData:
    """Parse form/JSON values, deriving order identity and metadata on the server."""
    order_type = data.get("order_type")
    if order_type not in ("by_id", "by_data"):
        raise InvalidTypeException("Select whether to order animals by ID or by data.")
    if order_type == "by_id" and any(_has_value(data.get(field)) for field in ("sex", "age", "amount")):
        raise InvalidTypeException("An ID order cannot also specify sex, age or amount.")
    if order_type == "by_data" and _has_value(data.get("ids")):
        raise InvalidTypeException("A data order cannot also specify animal IDs.")
    comment = data.get("comment", "")
    if not isinstance(comment, str):
        raise InvalidTypeException("Order comment must be text.")
    common: dict[str, Any] = {
        "licence": data.get("licence"), "line": data.get("line"),
        "date": _delivery_date(data.get("date")), "user": user.email, "comment": comment,
    }
    if order_type == "by_id":
        ids = data.get("ids")
        if isinstance(ids, str):
            ids = [identifier for identifier in re.split(r"[,\s]+", ids.strip()) if identifier]
        if not isinstance(ids, list):
            raise InvalidTypeException("An ID order requires a non-empty list of animal IDs.")
        return AnimalOrderById(**common, ids=ids)
    sex = data.get("sex")
    if not isinstance(sex, str):
        raise InvalidTypeException("Order sex must be female, male or unknown.")
    return AnimalOrderByData(
        **common, sex=sex,
        age=_required_integer(data.get("age"), "age in weeks", 0),
        amount=_required_integer(data.get("amount"), "amount", 1),
    )


def validate_order_submission(user: User, data: Mapping[str, Any]) -> AnimalOrder:
    """Return a validated, transient order for the caller to add and commit.

    Dates use YYYY-MM-DD (or date objects), integer fields accept form strings,
    and IDs accept a list or comma/whitespace-separated text. The user's email,
    timestamp and pending status are derived on the server.

    Remaining capacity is the configured allowance minus currently assigned
    AnimalData records, matching the settings page. Pending/approved orders
    do not reserve places: there is no import reconciliation for data orders
    yet. Call this in the submission transaction with current database data.
    """
    order = _order_from_submission(user, data)
    allowance = validate_order_selection(user, order.licence, order.line).num_availible_animals
    _validate_order_capacity(order, allowance)
    return order


def _validate_order_capacity(order: AnimalOrder, allowance: int | None) -> None:
    if allowance is None:
        raise OrderAllowanceNotConfigured(order.licence, order.line)
    used = get_animal_counts(*order.licence.split("/", 1)).get(order.line, 0)
    if isinstance(order, AnimalOrderById):
        requested = len(order.ids)
    elif isinstance(order, AnimalOrderByData):
        requested = order.amount
    else:
        raise InvalidTypeException("Unsupported order type.")
    if used + requested > allowance:
        raise OrderQuotaExceeded(order.licence, order.line, allowance, used, requested)


def _visible_orders(user: User) -> Query[AnimalOrder]:
    query = AnimalOrder.query
    if not user.paw_control:
        query = query.filter(AnimalOrder.user == user.email)
    return query


def get_orders(user: User, *, requester: str = "", status: str = "") -> list[AnimalOrder]:
    """List newest orders first, applying access restrictions before filters."""
    if status and status not in ("pending", "approved", "rejected"):
        raise InvalidTypeException("Order status filter must be pending, approved or rejected.")
    query = _visible_orders(user)
    if requester:
        if not user.paw_control and requester != user.email:
            raise Forbidden("You may only view your own orders.")
        query = query.filter(AnimalOrder.user == requester)
    if status:
        query = query.filter(AnimalOrder.status == status)
    return query.order_by(AnimalOrder.created_at.desc(), AnimalOrder.uuid.desc()).all()


def get_order_users(user: User) -> list[dict[str, str]]:
    """Requester filter choices for all visible orders, independent of filters.

    Keep historical orders accessible when an account has been deleted, using
    the stored email as the display name in that case.
    """
    emails = [row[0] for row in _visible_orders(user).with_entities(AnimalOrder.user).distinct().all()]
    names = {account.email: account.name for account in User.query.filter(User.email.in_(emails)).all()}
    return sorted(
        [{"email": email, "name": names.get(email) or email} for email in emails],
        key=lambda choice: (choice["name"].casefold(), choice["email"]),
    )


def get_order(user: User, order_uuid: str) -> AnimalOrder:
    """Return one visible order; another user's order is indistinguishable from a missing one."""
    order = _visible_orders(user).filter(AnimalOrder.uuid == order_uuid).first()
    if order is None:
        raise EntryNotFound("Order not found.")
    return order


def review_order(user: User, order_uuid: str, status: object) -> AnimalOrder:
    """Review a pending order, leaving commit/rollback to the request handler.

    Paw Control membership grants review access independently of licence
    membership. Approval rechecks the existing licence, line and capacity;
    rejection remains possible if those configurations were removed. The
    conditional update prevents a second reviewer from replacing a decision.
    """
    if not user.paw_control:
        raise Forbidden("Only Paw Control members can approve or reject orders.")
    if status not in ("approved", "rejected"):
        raise InvalidTypeException("Set order status to approved or rejected.")
    order = get_order(user, order_uuid)
    if order.status != "pending":
        raise OrderAlreadyReviewed()
    if status == "approved":
        _require_existing_order_licence(order.licence)
        _validate_order_capacity(order, _get_order_allowance(order.licence, order.line).num_availible_animals)
    updated = AnimalOrder.query.filter_by(uuid=order_uuid, status="pending").update(
        {"status": status}, synchronize_session="fetch",
    )
    if updated != 1:
        raise OrderAlreadyReviewed()
    return order
