import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import database_engine, session_factory
from app.models import Edition


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = database_engine() if os.environ.get("APP_DB_PASSWORD") else None
    app.state.sessions = session_factory(engine) if engine is not None else None
    try:
        yield
    finally:
        if engine is not None:
            engine.dispose()


app = FastAPI(
    title="The Kastle Daily",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readiness(request: Request):
    sessions = getattr(request.app.state, "sessions", None)
    if sessions is not None:
        try:
            with sessions() as session:
                session.execute(select(Edition.id).limit(1))
            return {"status": "ready"}
        except SQLAlchemyError:
            pass
    return JSONResponse(status_code=503, content={"status": "unavailable"})
