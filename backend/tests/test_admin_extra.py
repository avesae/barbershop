import io

import httpx
import pytest
from PIL import Image

from app import booking as bk
from app import db
from app.main import app

from .conftest import NOW

AUTH = ("admin", "secret")


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", auth=AUTH) as c:
        yield c


async def test_master_crud_and_hours(client):
    r = await client.post("/api/admin/masters", json={
        "name": "Олег", "title": "Стажёр", "service_ids": [2],
        "hours": [{"weekday": 0, "start": "10:00", "end": "14:00"}, {"weekday": 0, "start": "15:00", "end": "18:00"}],
    })
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["service_ids"] == [2] and len(m["hours"]) == 2

    slots = (await client.get("/api/slots", params={"master_id": m["id"], "service_id": 2, "day": "2026-11-09"})).json()
    assert "13:30" in slots and "14:00" not in slots and "15:00" in slots

    r = await client.put(f"/api/admin/masters/{m['id']}", json={
        "name": "Олег", "title": "Барбер", "service_ids": [1, 2], "hours": [{"weekday": 1, "start": "12:00", "end": "20:00"}],
    })
    assert r.json()["hours"] == [{"weekday": 1, "start": "12:00", "end": "20:00"}]
    assert (await client.get("/api/slots", params={"master_id": m["id"], "service_id": 2, "day": "2026-11-09"})).json() == []

    bad = await client.put(f"/api/admin/masters/{m['id']}", json={"name": "Олег", "hours": [{"weekday": 1, "start": "20:00", "end": "12:00"}]})
    assert bad.status_code == 422


async def test_master_invite(client):
    r = await client.post("/api/admin/masters/1/invite")
    assert r.json()["code"]


async def test_upload_and_gallery(client):
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), "brown").save(buf, "JPEG")
    r = await client.post("/api/admin/uploads", files={"file": ("cut.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 201
    url = r.json()["url"]
    img = await client.get(url)
    assert img.status_code == 200
    assert max(Image.open(io.BytesIO(img.content)).size) == 1600

    bad = await client.post("/api/admin/uploads", files={"file": ("x.txt", b"hello", "text/plain")})
    assert bad.status_code == 400

    w = (await client.post("/api/admin/works", json={"photo": url, "caption": "Фейд", "master_id": 1})).json()
    assert (await client.get("/api/works")).json() == [{"photo": url, "caption": "Фейд"}]
    assert (await client.post("/api/admin/works", json={"photo": "https://evil/x.png"})).status_code == 422
    assert (await client.delete(f"/api/admin/works/{w['id']}")).status_code == 204
    assert (await client.get(url)).status_code == 404


async def test_visit_status_and_client_card(client, monkeypatch):
    b = (await client.post("/api/bookings", json={
        "service_id": 1, "master_id": 1, "start_at": "2026-11-09T12:00:00",
        "name": "Иван", "phone": "+79001112233", "consent": True})).json()
    r = await client.post(f"/api/admin/bookings/{b['id']}/status", json={"status": "no_show"})
    assert r.status_code == 400  # визит ещё не начался

    monkeypatch.setattr(bk, "now_local", lambda: NOW.replace(hour=13))
    r = await client.post(f"/api/admin/bookings/{b['id']}/status", json={"status": "no_show"})
    assert r.json()["status"] == "no_show"

    [c] = (await client.get("/api/admin/clients", params={"q": "900111"})).json()
    assert (c["visits"], c["no_shows"], c["spent"]) == (0, 1, 0)
    assert (await client.get("/api/admin/clients", params={"q": "Пётр"})).json() == []

    await client.put(f"/api/admin/clients/{c['id']}/notes", json={"notes": "Короче на висках"})
    card = (await client.get(f"/api/admin/clients/{c['id']}")).json()
    assert card["notes"] == "Короче на висках"
    assert card["consent"]["version"] == "1.0" and card["consent"]["source"] == "site"
    assert card["history"][0]["status"] == "no_show"

    stats = (await client.get("/api/admin/stats", params={"days": 7})).json()
    assert stats["summary"]["no_show"] == 1 and stats["summary"]["no_show_rate"] == 100.0
    artem = next(m for m in stats["masters"] if m["name"] == "Артём")
    assert artem["load"] > 0


async def test_review_moderation(client):
    from datetime import timedelta

    from app import engagement as eg
    from app.models import Booking

    async with db.SessionLocal() as s:
        c = await bk.get_or_create_phone_client(s, "Иван", "+79001112233")
        b = Booking(client_id=c.id, master_id=1, service_id=1, start_at=NOW - timedelta(days=1),
                    end_at=NOW - timedelta(hours=23), price=1800, status="done", source="site")
        s.add(b)
        await s.commit()
        r = await eg.save_rating(s, b, 5)

    assert (await client.put(f"/api/admin/reviews/{r.id}", json={"published": True})).status_code == 400
    async with db.SessionLocal() as s:
        await eg.save_review_text(s, r.id, "Отлично!")
    assert (await client.get("/api/reviews")).json() == []
    assert (await client.put(f"/api/admin/reviews/{r.id}", json={"published": True})).json()["published"]
    [pub] = (await client.get("/api/reviews")).json()
    assert (pub["author"], pub["rating"], pub["master"]) == ("Иван", 5, "Артём")
    assert (await client.delete(f"/api/admin/reviews/{r.id}")).status_code == 204
    assert (await client.get("/api/reviews")).json() == []
