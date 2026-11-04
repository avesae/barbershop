import json
import time
from urllib.parse import urlencode

import httpx
import pytest
from sqlalchemy import select

from app import telegram_auth as ta
from app.config import get_settings
from app.main import app
from app.models import Booking, Consent

TOKEN = "123456:" + "B" * 35


def init_data(user_id=777, auth_date=None, token=TOKEN, tamper=False):
    fields = {
        "auth_date": str(int(auth_date or time.time())),
        "query_id": "AAH",
        "user": json.dumps({"id": user_id, "first_name": "Иван"}, ensure_ascii=False),
    }
    fields["hash"] = ta.sign(fields, token)
    if tamper:
        fields["user"] = json.dumps({"id": 1, "first_name": "Хакер"})
    return urlencode(fields)


def test_verify():
    assert ta.verify(init_data(), TOKEN)["id"] == 777
    for bad in [init_data(tamper=True), init_data(token="999:" + "C" * 35), "user=1", ""]:
        with pytest.raises(ta.InitDataError):
            ta.verify(bad, TOKEN)
    with pytest.raises(ta.InitDataError, match="устарела"):
        ta.verify(init_data(auth_date=time.time() - 2 * 86400), TOKEN)


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "bot_token", TOKEN)
    # сообщения в Telegram в тестах не отправляем
    import app.routers.tg_app as tg

    async def fake_send(*a, **kw):
        return True

    async def fake_owner(*a, **kw):
        return None

    monkeypatch.setattr(tg, "send", fake_send)
    monkeypatch.setattr(tg, "notify_owner", fake_owner)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def payload(**kw):
    data = {"service_id": 1, "master_id": 1, "start_at": "2026-11-09T12:00:00",
            "name": "Иван", "phone": "+79001112233", "consent": True}
    data.update(kw)
    return data


async def test_mini_app_booking(client):
    h = {"X-Telegram-Init-Data": init_data()}
    assert (await client.get("/api/tg/me")).status_code == 401
    me = (await client.get("/api/tg/me", headers=h)).json()
    assert me == {**me, "name": "Иван", "phone": None, "consent": False}

    assert (await client.post("/api/tg/bookings", json=payload(consent=False), headers=h)).status_code == 400
    r = await client.post("/api/tg/bookings", json=payload(), headers=h)
    assert r.status_code == 201, r.text
    me = (await client.get("/api/tg/me", headers=h)).json()
    assert me["consent"] and me["phone"] == "+79001112233"

    # второй раз согласие уже есть — галочка не нужна
    r = await client.post("/api/tg/bookings", json=payload(start_at="2026-11-09T15:00:00", consent=False), headers=h)
    assert r.status_code == 201
    r = await client.post("/api/tg/bookings", json=payload(start_at="2026-11-09T15:00:00"), headers=h)
    assert r.status_code == 409

    from app import db
    async with db.SessionLocal() as s:
        assert len((await s.execute(select(Consent))).scalars().all()) == 1
        assert {b.source for b in (await s.execute(select(Booking))).scalars()} == {"bot"}
