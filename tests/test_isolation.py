from app.rag.retrieve import RETRIEVE_SQL, retrieve_chunks


def test_retrieval_sql_requires_company_id():
    sql = " ".join(RETRIEVE_SQL.split())
    assert "c.company_id = %s" in sql
    assert "d.company_id = %s" in sql
    assert "d.status = 'READY'" in sql
    assert "d.visibility = 'ALL_EMPLOYEES' OR %s = 'ADMIN'" in sql
    assert sql.lower().count("company_id") >= 2


def test_retrieve_passes_company_id_twice(monkeypatch):
    captured: dict = {}

    class FakeResult:
        def fetchall(self):
            return []

    class FakeConn:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return FakeResult()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.rag.retrieve.llm.embed", lambda texts: [[0.1] * 8])
    monkeypatch.setattr("app.rag.retrieve.db.tenant_connection", lambda company_id: FakeConn())
    monkeypatch.setattr("app.rag.retrieve.get_settings", lambda: type("S", (), {"similarity_floor": 0.0, "retrieve_top_k": 5})())

    retrieve_chunks("company-a", "How many annual leaves do I get?", role="EMPLOYEE")
    params = captured["params"]
    assert params[1] == "company-a"
    assert params[2] == "company-a"
    assert params[1] == params[2]
    assert params[3] == "EMPLOYEE"


def test_employee_does_not_receive_admin_only_chunks(monkeypatch):
    class FakeResult:
        def fetchall(self):
            return [
                {
                    "document_id": "doc-admin",
                    "document_name": "Salaries.pdf",
                    "visibility": "ADMIN_ONLY",
                    "content": "Ahmed salary is 250000",
                    "page_number": 1,
                    "chunk_index": 0,
                    "distance": 0.05,
                },
                {
                    "document_id": "doc-all",
                    "document_name": "Leave Policy.md",
                    "visibility": "ALL_EMPLOYEES",
                    "content": "24 annual leaves",
                    "page_number": 1,
                    "chunk_index": 0,
                    "distance": 0.1,
                },
            ]

    class FakeConn:
        def execute(self, sql, params):
            return FakeResult()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.rag.retrieve.llm.embed", lambda texts: [[0.1] * 8])
    monkeypatch.setattr("app.rag.retrieve.db.tenant_connection", lambda company_id: FakeConn())
    monkeypatch.setattr("app.rag.retrieve.get_settings", lambda: type("S", (), {"similarity_floor": 0.0, "retrieve_top_k": 5})())

    employee_chunks = retrieve_chunks("company-a", "What is Ahmed's salary?", role="EMPLOYEE")
    assert [chunk["document"] for chunk in employee_chunks] == ["Leave Policy.md"]
    assert all("salary" not in chunk["content"].lower() for chunk in employee_chunks)

    admin_chunks = retrieve_chunks("company-a", "What is Ahmed's salary?", role="ADMIN")
    assert [chunk["document"] for chunk in admin_chunks] == ["Salaries.pdf", "Leave Policy.md"]


def test_retrieve_embeds_conversation_history(monkeypatch):
    captured: dict = {}

    class FakeResult:
        def fetchall(self):
            return []

    class FakeConn:
        def execute(self, sql, params):
            return FakeResult()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_embed(texts):
        captured["texts"] = texts
        return [[0.1] * 8]

    monkeypatch.setattr("app.rag.retrieve.llm.embed", fake_embed)
    monkeypatch.setattr("app.rag.retrieve.db.tenant_connection", lambda company_id: FakeConn())
    monkeypatch.setattr("app.rag.retrieve.get_settings", lambda: type("S", (), {"similarity_floor": 0.0, "retrieve_top_k": 5})())

    retrieve_chunks(
        "company-a",
        "What about maternity leave?",
        role="EMPLOYEE",
        history="Employee: How many annual leaves do I get?",
    )
    assert "Current question: What about maternity leave?" in captured["texts"][0]
    assert "How many annual leaves do I get?" in captured["texts"][0]


def test_tenant_connection_sets_local_company_id(monkeypatch):
    from contextlib import contextmanager

    captured: list[tuple] = []

    class FakeConn:
        def execute(self, sql, params=None):
            captured.append((sql, params))
            return self

        def commit(self):
            captured.append(("COMMIT", None))

    @contextmanager
    def fake_connection():
        yield FakeConn()

    monkeypatch.setattr("app.db.connection", fake_connection)

    from app.db import tenant_connection

    with tenant_connection("company-a") as conn:
        conn.execute("SELECT 1")
        conn.commit()
        conn.execute("SELECT 2")

    guc_calls = [item for item in captured if "set_config('app.company_id'" in str(item[0])]
    assert len(guc_calls) >= 2
    assert guc_calls[0][1] == ("company-a",)


def test_tenant_connection_sets_non_bypass_role(monkeypatch):
    from contextlib import contextmanager

    captured: list[str] = []

    class FakeConn:
        def execute(self, sql, params=None):
            captured.append(str(sql))
            return self

        def commit(self):
            captured.append("COMMIT")

    @contextmanager
    def fake_connection():
        yield FakeConn()

    monkeypatch.setattr("app.db.connection", fake_connection)
    from app.db import tenant_connection

    with tenant_connection("company-a") as conn:
        conn.execute("SELECT 1")

    assert any("SET LOCAL ROLE hr_app" in sql for sql in captured)
    assert any("set_config('app.company_id'" in sql for sql in captured)


def test_rls_policies_require_company_guc_and_force():
    from pathlib import Path

    schema = Path("app/db/schema.sql").read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in schema
    assert "current_setting('app.company_id'" in schema
    assert schema.count("ENABLE ROW LEVEL SECURITY") >= 4


def test_document_index_version_changes_when_a_document_is_deleted():
    from app.services.chat_service import DOCUMENT_INDEX_VERSION_SQL

    sql = " ".join(DOCUMENT_INDEX_VERSION_SQL.split())
    assert "COUNT(*)" in sql
    assert "string_agg(id::text" in sql
    assert "MAX(updated_at)" in sql
    assert "company_id = %s" in sql
