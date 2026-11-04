"""Демо-данные: заполняются один раз, если в базе ещё нет услуг."""

from datetime import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Master, Service, WorkingHours

SERVICES = [
    ("Мужская стрижка", "Консультация, мытьё головы, стрижка и укладка", 1800, 60),
    ("Стрижка машинкой", "Одна насадка по всей голове, окантовка", 1000, 30),
    ("Фейд", "Плавный переход от кожи, укладка", 2000, 60),
    ("Моделирование бороды", "Форма, контур опасной бритвой, уход маслом", 1200, 30),
    ("Стрижка + борода", "Комплекс: стрижка и оформление бороды", 2800, 90),
    ("Королевское бритьё", "Распаривание горячим полотенцем, бритьё опасной бритвой", 1500, 45),
]

# имя, должность, описание, индексы услуг, рабочие дни, часы
MASTERS = [
    ("Артём", "Топ-барбер", "10 лет за креслом. Классические стрижки и сложные фейды.",
     [0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4], (time(10), time(20))),
    ("Тимур", "Барбер", "Мастер бороды и королевского бритья.",
     [0, 1, 3, 4, 5], [1, 2, 3, 4, 5], (time(11), time(21))),
    ("Даниил", "Барбер", "Короткие стрижки и аккуратные переходы.",
     [0, 1, 2, 4], [0, 2, 4, 5, 6], (time(10), time(19))),
]


async def seed(session: AsyncSession) -> None:
    if await session.scalar(select(func.count()).select_from(Service)):
        return
    services = [
        Service(name=n, description=d, price=p, duration_min=m, sort=i)
        for i, (n, d, p, m) in enumerate(SERVICES)
    ]
    session.add_all(services)
    for name, title, bio, svc_idx, days, (start, end) in MASTERS:
        session.add(
            Master(
                name=name,
                title=title,
                bio=bio,
                services=[services[i] for i in svc_idx],
                working_hours=[WorkingHours(weekday=d, start=start, end=end) for d in days],
            )
        )
    await session.commit()
