from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from fastapi import HTTPException

from app import db
from app.schemas import CompanyOut, EmployeeOut, UserOut
from app.security import AuthUser, hash_password, verify_password

logger = logging.getLogger(__name__)

USER_SELECT = """
SELECT
  u.id,
  u.company_id,
  u.email,
  u.password_hash,
  u.name,
  u.role,
  c.name AS company_name,
  c.slug AS company_slug
FROM users u
JOIN companies c ON c.id = u.company_id
"""


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "company"


def unique_slug(conn, name: str) -> str:
    base = slugify(name)
    slug = base
    suffix = 2
    while conn.execute("SELECT 1 FROM companies WHERE slug = %s", (slug,)).fetchone():
        slug = f"{base}-{suffix}"[:64]
        suffix += 1
    return slug


def user_from_row(row: dict) -> AuthUser:
    return AuthUser(
        id=str(row["id"]),
        company_id=str(row["company_id"]),
        email=row["email"],
        name=row["name"],
        role=row["role"],
        company_name=row["company_name"],
        company_slug=row["company_slug"],
    )


def to_user_out(user: AuthUser) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,  # type: ignore[arg-type]
        company=CompanyOut(id=user.company_id, name=user.company_name, slug=user.company_slug),
    )


def get_user_by_id(user_id: str) -> AuthUser | None:
    with db.connection() as conn:
        row = conn.execute(USER_SELECT + " WHERE u.id = %s", (user_id,)).fetchone()
    return user_from_row(dict(row)) if row else None


def get_user_by_email(email: str) -> dict | None:
    with db.connection() as conn:
        row = conn.execute(USER_SELECT + " WHERE lower(u.email) = lower(%s)", (email,)).fetchone()
    return dict(row) if row else None


def register_company_admin(company_name: str, name: str, email: str, password: str) -> AuthUser:
    with db.connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(%s)",
            (email,),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists")

        company_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        slug = unique_slug(conn, company_name)
        conn.execute(
            "INSERT INTO companies (id, name, slug) VALUES (%s, %s, %s)",
            (company_id, company_name.strip(), slug),
        )
        conn.execute(
            """
            INSERT INTO users (id, company_id, email, password_hash, name, role)
            VALUES (%s, %s, %s, %s, %s, 'ADMIN')
            """,
            (user_id, company_id, email.lower().strip(), hash_password(password), name.strip()),
        )
        conn.commit()

    logger.info("Registered company %s with admin %s", slug, user_id)
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=500, detail="Could not load the new account")
    return user


def authenticate(email: str, password: str) -> AuthUser:
    row = get_user_by_email(email)
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return user_from_row(row)


def create_employee(company_id: str, name: str, email: str, password: str) -> EmployeeOut:
    with db.connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(%s)",
            (email,),
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO users (id, company_id, email, password_hash, name, role)
            VALUES (%s, %s, %s, %s, %s, 'EMPLOYEE')
            """,
            (user_id, company_id, email.lower().strip(), hash_password(password), name.strip()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, email, name, role, created_at FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    return _employee_out(dict(row))


def list_employees(company_id: str) -> list[EmployeeOut]:
    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT id, email, name, role, created_at
            FROM users
            WHERE company_id = %s
            ORDER BY created_at ASC
            """,
            (company_id,),
        ).fetchall()
    return [_employee_out(dict(row)) for row in rows]


def _employee_out(row: dict) -> EmployeeOut:
    created = row["created_at"]
    created_at = created.isoformat() if isinstance(created, datetime) else str(created)
    if created_at.endswith("+00:00"):
        created_at = created_at.replace("+00:00", "Z")
    return EmployeeOut(
        id=str(row["id"]),
        email=row["email"],
        name=row["name"],
        role=row["role"],
        created_at=created_at,
    )
