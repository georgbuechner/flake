"""Data shapes shared by database access and document generation."""
from typing import Any, Protocol, TypedDict


class NamedEntry(Protocol):
    @property
    def name(self) -> str: ...


class ExperimentData(TypedDict):
    general: dict[str, Any]
    medication: list[dict[str, Any]]
    procedures: list[dict[str, Any]]
    viruses: list[dict[str, Any]]


class SurgerySheetData(ExperimentData, total=False):
    death_drugs: list[dict[str, Any]]


class ProcedureSummary(TypedDict):
    name: str
    start_date: str
    end_date: str
