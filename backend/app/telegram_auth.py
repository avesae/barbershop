"""Проверка initData из Telegram Mini App.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE_SEC = 24 * 3600


class InitDataError(Exception):
    pass


def sign(fields: dict[str, str], bot_token: str) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def verify(init_data: str, bot_token: str, *, now: float | None = None) -> dict:
    """Возвращает пользователя Telegram ({"id": ..., "first_name": ...}) или бросает InitDataError."""
    if not bot_token:
        raise InitDataError("Бот не настроен")
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received = fields.pop("hash", "")
    if not received or not hmac.compare_digest(sign(fields, bot_token), received):
        raise InitDataError("Неверная подпись")
    try:
        auth_date = int(fields.get("auth_date", "0"))
        user = json.loads(fields["user"])
    except (ValueError, KeyError):
        raise InitDataError("Нет данных пользователя") from None
    if (now or time.time()) - auth_date > MAX_AGE_SEC:
        raise InitDataError("Сессия устарела, откройте приложение заново")
    if not isinstance(user, dict) or "id" not in user:
        raise InitDataError("Нет данных пользователя")
    return user
