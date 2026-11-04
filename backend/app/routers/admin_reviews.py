"""Админка: модерация отзывов."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_session, require_admin
from ..models import Review

router = APIRouter(prefix="/api/admin/reviews", tags=["admin"], dependencies=[Depends(require_admin)])


def review_out(r: Review) -> dict:
    return {
        "id": r.id, "rating": r.rating, "text": r.text, "author": r.author, "master": r.master.name,
        "service": r.booking.service.name, "created_at": r.created_at, "published": r.published,
        "client_id": r.client_id,
    }


@router.get("")
async def reviews(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await session.execute(select(Review).order_by(Review.created_at.desc()).limit(200))
    return [review_out(r) for r in rows.scalars()]


class PublishIn(BaseModel):
    published: bool


@router.put("/{review_id}")
async def publish(review_id: int, data: PublishIn, session: AsyncSession = Depends(get_session)) -> dict:
    r = await session.get(Review, review_id)
    if not r:
        raise HTTPException(404, "Отзыв не найден")
    if data.published and not r.text:
        raise HTTPException(400, "Публикуются только отзывы с текстом")
    r.published = data.published
    await session.commit()
    return review_out(r)


@router.delete("/{review_id}", status_code=204)
async def delete(review_id: int, session: AsyncSession = Depends(get_session)) -> None:
    r = await session.get(Review, review_id)
    if not r:
        raise HTTPException(404, "Отзыв не найден")
    await session.delete(r)
    await session.commit()
