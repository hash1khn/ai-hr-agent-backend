from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator

Role = Literal["ADMIN", "EMPLOYEE"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _parse_email(value: str) -> str:
    email = value.strip().lower()
    if not _EMAIL.match(email) or len(email) > 254:
        raise ValueError("Enter a valid email address")
    return email


EmailAddress = Annotated[str, AfterValidator(_parse_email)]
