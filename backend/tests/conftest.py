import os
import tempfile
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["BOT_TOKEN"] = ""
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "secret"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="barber-uploads-")

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import booking as bk
from app import db
from app.seed import seed

# Понедельник, 9:00. Артём (id=1) работает пн–пт 10–20.
NOW = datetime(2026, 11, 9, 9, 0)


@pytest.fixture(autouse=True)
async def database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(bk, "now_local", lambda: NOW)
    await db.init_db(engine)
    async with db.SessionLocal() as s:
        await seed(s)
    yield
    await engine.dispose()


@pytest.fixture
async def session():
    async with db.SessionLocal() as s:
        yield s
