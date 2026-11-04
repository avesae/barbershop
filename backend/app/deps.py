import secrets
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from . import db
from .config import get_settings

basic = HTTPBasic(auto_error=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with db.SessionLocal() as session:
        yield session


def require_admin(creds: HTTPBasicCredentials | None = Depends(basic)) -> None:
    s = get_settings()
    ok = (
        creds is not None
        and secrets.compare_digest(creds.username.encode(), s.admin_user.encode())
        and secrets.compare_digest(creds.password.encode(), s.admin_password.encode())
    )
    if not ok:
        # Без заголовка WWW-Authenticate, чтобы браузер не показывал своё окно входа.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
