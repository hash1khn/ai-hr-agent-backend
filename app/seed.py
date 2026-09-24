from __future__ import annotations

import logging
from pathlib import Path

from app import db
from app.core.config import get_settings
from app.core.security import hash_password
from app.services import document_service

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

ACME_COMPANY_ID = "11111111-1111-1111-1111-111111111111"
ACME_ADMIN_ID = "22222222-2222-2222-2222-222222222222"
ACME_EMPLOYEE_ID = "33333333-3333-3333-3333-333333333333"

ADMIN_EMAIL = "admin@acme.test"
EMPLOYEE_EMAIL = "employee@acme.test"
ADMIN_PASSWORD = "AcmeAdmin123!"
EMPLOYEE_PASSWORD = "AcmeEmployee123!"


def ensure_demo_company() -> None:
    with db.connection() as conn:
        existing = conn.execute(
            "SELECT id FROM companies WHERE slug = %s",
            ("acme-technologies",),
        ).fetchone()
        if existing:
            logger.info("Demo company already present")
            return

        conn.execute(
            "INSERT INTO companies (id, name, slug) VALUES (%s, %s, %s)",
            (ACME_COMPANY_ID, "Acme Technologies", "acme-technologies"),
        )
        conn.execute(
            """
            INSERT INTO users (id, company_id, email, password_hash, name, role)
            VALUES (%s, %s, %s, %s, %s, 'ADMIN')
            """,
            (
                ACME_ADMIN_ID,
                ACME_COMPANY_ID,
                ADMIN_EMAIL,
                hash_password(ADMIN_PASSWORD),
                "Amina Khan",
            ),
        )
        conn.execute(
            """
            INSERT INTO users (id, company_id, email, password_hash, name, role)
            VALUES (%s, %s, %s, %s, %s, 'EMPLOYEE')
            """,
            (
                ACME_EMPLOYEE_ID,
                ACME_COMPANY_ID,
                EMPLOYEE_EMAIL,
                hash_password(EMPLOYEE_PASSWORD),
                "Omar Farooq",
            ),
        )
        conn.commit()

    logger.info("Created demo company Acme Technologies")
    ingest_fixtures()


def ingest_fixtures(company_id: str = ACME_COMPANY_ID) -> None:
    if not get_settings().api_key:
        logger.warning("Skipping fixture ingest because no LLM API key is configured")
        return
    if not FIXTURES_DIR.is_dir():
        logger.warning("fixtures directory not found")
        return
    existing = document_service.list_documents(company_id)
    if existing:
        logger.info("Demo documents already present")
        return

    files = sorted(
        file
        for file in FIXTURES_DIR.iterdir()
        if file.suffix in {".md", ".txt"} and file.is_file()
    )
    for file in files:
        original = _display_name(file)
        try:
            document_service.ingest_text(
                company_id=company_id,
                original_name=original,
                text=file.read_text(encoding="utf-8"),
            )
        except Exception:
            logger.exception("Failed to ingest fixture %s", file.name)


def _display_name(file: Path) -> str:
    mapping = {
        "employee-handbook.md": "Employee Handbook.md",
        "leave-policy.md": "Leave Policy.md",
        "attendance-policy.md": "Attendance Policy.md",
        "benefits-policy.md": "Benefits Policy.md",
    }
    return mapping.get(file.name, file.name.replace("-", " ").title())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db.connect()
    try:
        ensure_demo_company()
        ingest_fixtures()
    finally:
        db.close()
