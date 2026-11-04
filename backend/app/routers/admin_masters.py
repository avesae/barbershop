"""Админка: мастера, их рабочие часы, приглашение в бот, фото и галерея работ."""

import secrets
from datetime import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..deps import get_session, require_admin
from ..media import MediaError, delete_image, save_image
from ..models import Master, Service, WorkingHours, Work

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class HoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: time
    end: time

    @model_validator(mode="after")
    def check(self):
        if self.end <= self.start:
            raise ValueError("Конец смены должен быть позже начала")
        return self


class MasterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    title: str = Field(default="Барбер", max_length=100)
    bio: str = ""
    photo: str | None = None
    is_active: bool = True
    service_ids: list[int] = []
    hours: list[HoursIn] = []


def master_out(m: Master) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "title": m.title,
        "bio": m.bio,
        "photo": m.photo,
        "is_active": m.is_active,
        "service_ids": sorted(s.id for s in m.services),
        "hours": [
            {"weekday": w.weekday, "start": w.start.strftime("%H:%M"), "end": w.end.strftime("%H:%M")}
            for w in sorted(m.working_hours, key=lambda w: (w.weekday, w.start))
        ],
        "telegram": m.tg_user_id is not None,
    }


async def _master(session: AsyncSession, master_id: int) -> Master:
    m = await session.get(
        Master,
        master_id,
        options=[selectinload(Master.services), selectinload(Master.working_hours)],
        populate_existing=True,
    )
    if not m:
        raise HTTPException(404, "Мастер не найден")
    return m


@router.get("/masters")
async def masters(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await session.execute(select(Master).order_by(Master.id))
    return [master_out(m) for m in rows.scalars()]


async def _apply(session: AsyncSession, m: Master, data: MasterIn) -> dict:
    q = select(Service).where(Service.id.in_(data.service_ids)).options(selectinload(Service.masters))
    services = list((await session.execute(q)).scalars())
    if m.photo and m.photo != data.photo:
        delete_image(m.photo)
    m.name, m.title, m.bio, m.photo, m.is_active = data.name, data.title, data.bio, data.photo, data.is_active
    m.services = services
    m.working_hours = [WorkingHours(weekday=h.weekday, start=h.start, end=h.end) for h in data.hours]
    session.add(m)
    await session.commit()
    return master_out(await _master(session, m.id))


@router.post("/masters", status_code=201)
async def create_master(data: MasterIn, session: AsyncSession = Depends(get_session)) -> dict:
    return await _apply(session, Master(services=[], working_hours=[]), data)


@router.put("/masters/{master_id}")
async def update_master(master_id: int, data: MasterIn, session: AsyncSession = Depends(get_session)) -> dict:
    return await _apply(session, await _master(session, master_id), data)


@router.post("/masters/{master_id}/invite")
async def invite_master(master_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """Одноразовая ссылка: мастер открывает её в Telegram и получает кабинет."""
    m = await _master(session, master_id)
    m.invite_code = secrets.token_urlsafe(12)
    await session.commit()
    username = get_settings().bot_username
    return {
        "code": m.invite_code,
        "link": f"https://t.me/{username}?start=m_{m.invite_code}" if username else None,
    }


@router.delete("/masters/{master_id}/telegram", status_code=204)
async def unlink_master(master_id: int, session: AsyncSession = Depends(get_session)) -> None:
    m = await _master(session, master_id)
    m.tg_user_id = None
    m.invite_code = None
    await session.commit()


# --- фото ------------------------------------------------------------------


@router.post("/uploads", status_code=201)
async def upload(file: UploadFile) -> dict:
    try:
        return {"url": save_image(await file.read())}
    except MediaError as e:
        raise HTTPException(400, str(e))


class WorkIn(BaseModel):
    photo: str = Field(pattern=r"^/uploads/[\w.-]+$")
    caption: str = Field(default="", max_length=200)
    master_id: int | None = None


def work_out(w: Work) -> dict:
    return {"id": w.id, "photo": w.photo, "caption": w.caption, "master_id": w.master_id}


@router.get("/works")
async def works(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await session.execute(select(Work).order_by(Work.id.desc()))
    return [work_out(w) for w in rows.scalars()]


@router.post("/works", status_code=201)
async def add_work(data: WorkIn, session: AsyncSession = Depends(get_session)) -> dict:
    w = Work(photo=data.photo, caption=data.caption, master_id=data.master_id)
    session.add(w)
    await session.commit()
    return work_out(w)


@router.delete("/works/{work_id}", status_code=204)
async def delete_work(work_id: int, session: AsyncSession = Depends(get_session)) -> None:
    w = await session.get(Work, work_id)
    if not w:
        raise HTTPException(404, "Фото не найдено")
    delete_image(w.photo)
    await session.delete(w)
    await session.commit()
