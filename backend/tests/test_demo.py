from datetime import timedelta

import httpx
from sqlalchemy import func, select

from app import db, demo
from app.config import get_settings
from app.main import app
from app.models import Booking, Review

from .conftest import NOW


async def test_seed_demo_is_consistent(session):
    await demo.seed_demo(session, NOW)
    bookings = list((await session.execute(select(Booking))).scalars())
    assert len(bookings) > 100
    # Без пересечений у мастера среди неотменённых записей.
    live = sorted((b for b in bookings if b.status != "cancelled"), key=lambda b: (b.master_id, b.start_at))
    for a, b in zip(live, live[1:]):
        if a.master_id == b.master_id:
            assert a.end_at <= b.start_at
    assert all(b.status == "active" for b in bookings if b.start_at > NOW and b.status != "cancelled")
    assert all(b.status != "active" for b in bookings if b.start_at < NOW - timedelta(hours=2))
    assert await session.scalar(select(func.count()).select_from(Review).where(Review.published)) > 3


async def test_reset_demo_and_info(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    await demo.reset_demo()
    async with db.SessionLocal() as s:
        first = await s.scalar(select(func.count()).select_from(Booking))
    await demo.reset_demo()
    async with db.SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(Booking)) == first
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        info = (await c.get("/api/info")).json()
    assert info["demo"] == {"user": "admin", "password": "secret"}


async def test_info_hides_credentials_outside_demo():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/info")).json()["demo"] is None
