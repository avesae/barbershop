import httpx
import pytest

from app.main import app

AUTH = ("admin", "secret")


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def payload(**kw):
    data = {"service_id": 1, "master_id": 1, "start_at": "2026-11-09T12:00:00",
            "name": "Иван", "phone": "+7 900 111-22-33", "consent": True}
    data.update(kw)
    return data


async def test_public_catalog(client):
    services = (await client.get("/api/services")).json()
    masters = (await client.get("/api/masters")).json()
    assert len(services) == 6 and services[0]["master_ids"]
    assert {m["name"] for m in masters} == {"Артём", "Тимур", "Даниил"}
    info = (await client.get("/api/info")).json()
    assert info["consent_version"] == "1.0" and "персональных данных" in info["consent_text"]


async def test_site_booking_flow(client):
    dates = (await client.get("/api/dates", params={"master_id": 1, "service_id": 1})).json()
    assert dates[0] == "2026-11-09"
    slots = (await client.get("/api/slots", params={"master_id": 1, "service_id": 1, "day": "2026-11-09"})).json()
    assert "12:00" in slots

    r = await client.post("/api/bookings", json=payload(consent=False))
    assert r.status_code == 400
    r = await client.post("/api/bookings", json=payload(phone="12345"))
    assert r.status_code == 400
    r = await client.post("/api/bookings", json=payload())
    assert r.status_code == 201, r.text
    r = await client.post("/api/bookings", json=payload())
    assert r.status_code == 409

    slots = (await client.get("/api/slots", params={"master_id": 1, "service_id": 1, "day": "2026-11-09"})).json()
    assert "12:00" not in slots


async def test_admin_requires_auth(client):
    assert (await client.get("/api/admin/stats")).status_code == 401
    assert (await client.get("/api/admin/stats", auth=("admin", "wrong"))).status_code == 401


async def test_admin_flow(client):
    booking = (await client.post("/api/bookings", json=payload())).json()
    sched = (await client.get("/api/admin/schedule", params={"day": "2026-11-09", "days": 7}, auth=AUTH)).json()
    assert [b["id"] for b in sched["bookings"]] == [booking["id"]]
    assert sched["bookings"][0]["client_phone"] == "+79001112233"

    r = await client.post("/api/admin/time-off", auth=AUTH,
                          json={"master_id": 1, "day": "2026-11-09", "start": "14:00", "end": "15:00", "reason": "Обед"})
    assert r.status_code == 201
    slots = (await client.get("/api/slots", params={"master_id": 1, "service_id": 1, "day": "2026-11-09"})).json()
    assert "14:00" not in slots
    assert (await client.delete(f"/api/admin/time-off/{r.json()['id']}", auth=AUTH)).status_code == 204

    r = await client.post("/api/admin/services", auth=AUTH,
                          json={"name": "Камуфляж седины", "price": 900, "duration_min": 30, "master_ids": [1]})
    assert r.status_code == 201 and r.json()["master_ids"] == [1]
    sid = r.json()["id"]
    r = await client.put(f"/api/admin/services/{sid}", auth=AUTH,
                         json={"name": "Камуфляж седины", "price": 1100, "duration_min": 30, "master_ids": [1, 2]})
    assert r.json()["price"] == 1100 and r.json()["master_ids"] == [1, 2]

    stats = (await client.get("/api/admin/stats", auth=AUTH)).json()
    assert stats["week_total"] == 1 and stats["services_30d"][0]["name"] == "Мужская стрижка"

    r = await client.post(f"/api/admin/bookings/{booking['id']}/cancel", auth=AUTH)
    assert r.json()["status"] == "cancelled"
