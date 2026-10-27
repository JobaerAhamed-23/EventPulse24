"""The API error wire shape. Endpoints declare it, e.g. `response={404: ErrorOut}` (AD-19)."""

from typing import Any

from ninja import Schema


class ErrorItem(Schema):
    """One validation error. `loc` is the path to the field; empty for whole-object errors."""

    loc: list[str | int]
    msg: str


class ErrorOut(Schema):
    """`{code, message, details?}`. Validation errors use `details = {"errors": [ErrorItem]}`."""

    code: str
    message: str
    details: dict[str, Any] | None = None
