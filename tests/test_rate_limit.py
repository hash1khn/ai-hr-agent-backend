from fastapi import HTTPException

from app.rate_limit import _hits, enforce_auth_rate_limit, enforce_chat_rate_limit


class FakeRequest:
    def __init__(self, token: str):
        self.cookies = {"hr_session": token}
        self.headers = {}
        self.client = type("C", (), {"host": "127.0.0.1"})()


def test_chat_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "app.rate_limit.get_settings",
        lambda: type(
            "S",
            (),
            {
                "chat_rate_limit_per_minute": 2,
                "auth_rate_limit_per_minute": 10,
                "cookie_name": "hr_session",
            },
        )(),
    )
    _hits.clear()
    request = FakeRequest("token-a")
    enforce_chat_rate_limit(request)
    enforce_chat_rate_limit(request)
    try:
        enforce_chat_rate_limit(request)
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 429
    assert raised


def test_auth_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "app.rate_limit.get_settings",
        lambda: type(
            "S",
            (),
            {
                "chat_rate_limit_per_minute": 20,
                "auth_rate_limit_per_minute": 2,
                "cookie_name": "hr_session",
            },
        )(),
    )
    _hits.clear()
    request = FakeRequest("token-a")
    enforce_auth_rate_limit(request)
    enforce_auth_rate_limit(request)
    try:
        enforce_auth_rate_limit(request)
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 429
    assert raised


def test_rate_limiter_evicts_stale_keys(monkeypatch):
    from app import rate_limit

    _hits.clear()
    _hits["old"] = rate_limit.deque([0.0])
    rate_limit._last_sweep = 0.0
    rate_limit._sweep_stale(rate_limit.time())
    assert "old" not in _hits
