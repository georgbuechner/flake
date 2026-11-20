"""Animal usage shared by protocol settings and order quota checks."""
from data_manager.tables import AnimalData, db


def get_animal_counts(escaped_protocol: str, subprotocol: str) -> dict[str, int]:
    """Count assigned animals per line across all users, dates and life states.

    These are cumulative licence allowances; death or completion does not free
    a place in the allowance. Assignment is determined by the same protocol
    and subprotocol fields used by the protocol settings page.
    """
    return dict(db.session.query(AnimalData.line, db.func.count()).filter(
        AnimalData.protocol_escaped == escaped_protocol,
        AnimalData.subprotocol == subprotocol,
    ).group_by(AnimalData.line).all())
