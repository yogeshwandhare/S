"""Consistent Enum column helper.

SQLAlchemy's `Enum(..., native_enum=False)` stores the Python enum member's
`.name` by default (e.g. "ADMIN"), not its `.value` ("admin"). Since every
enum in this schema is a `str` subclass whose value IS the API-facing
string, storing `.name` would silently diverge from what the API returns
and what raw SQL/analytics queries expect. `str_enum` always stores/reads
`.value` instead.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


def str_enum[E: enum.Enum](enum_cls: type[E], length: int = 30) -> SAEnum:
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda obj: [e.value for e in obj],
    )
