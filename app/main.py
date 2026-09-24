from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db, seed
from app.api.router import api_router
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.validate_runtime_security()
    db.connect()
    try:
        if get_settings().seed_on_start:
            seed.ensure_demo_company()
    except Exception:
        logger.exception("Demo seed skipped")
    yield
    db.close()


app = FastAPI(title="AI HR Agent", version="1.0.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(RuntimeError)
def runtime_error_handler(_request, exc: RuntimeError):
    message = str(exc)
    status = 503 if "Postgres" in message else 500
    return JSONResponse(status_code=status, content={"detail": message})


@app.get("/health")
def health():
    return {"status": "ok", "service": "ai-hr-agent"}


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=get_settings().port, reload=True)


if __name__ == "__main__":
    run()
