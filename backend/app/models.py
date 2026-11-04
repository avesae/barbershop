"""Модели БД. Время хранится «наивным» в часовом поясе барбершопа (SHOP_TZ)."""

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


master_services = Table(
    "master_services",
    Base.metadata,
    Column("master_id", ForeignKey("masters.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(100), default="Барбер")
    bio: Mapped[str] = mapped_column(Text, default="")
    photo: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Кабинет мастера в боте: привязка по одноразовому коду-приглашению.
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    invite_code: Mapped[str | None] = mapped_column(String(32), unique=True)

    services: Mapped[list["Service"]] = relationship(
        secondary=master_services, back_populates="masters", lazy="selectin"
    )
    working_hours: Mapped[list["WorkingHours"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int] = mapped_column(Integer)
    duration_min: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    # Через сколько дней после визита предложить записаться снова.
    rebook_days: Mapped[int] = mapped_column(Integer, default=28)

    masters: Mapped[list[Master]] = relationship(
        secondary=master_services, back_populates="services", lazy="selectin"
    )


class WorkingHours(Base):
    """Рабочий интервал мастера в день недели (0 — понедельник). Нет строки — выходной."""

    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)


class TimeOff(Base):
    """Закрытое время: обед, выходной, отпуск."""

    __tablename__ = "time_off"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(100), default="")

    master: Mapped[Master] = relationship(lazy="joined")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Consent(Base):
    """Журнал согласий: кто, когда, на какую версию текста, где."""

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(10))  # site | bot
    accepted_at: Mapped[datetime] = mapped_column(DateTime)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL после удаления данных клиента: обезличенная запись остаётся для статистики.
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), index=True
    )
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[int] = mapped_column(Integer)
    # active — предстоит или ещё не отмечена; done — пришёл; no_show — не пришёл; cancelled
    status: Mapped[str] = mapped_column(String(20), default="active")
    source: Mapped[str] = mapped_column(String(10))  # site | bot
    reminded_24h: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_2h: Mapped[bool] = mapped_column(Boolean, default=False)
    review_asked: Mapped[bool] = mapped_column(Boolean, default=False)
    rebook_offered: Mapped[bool] = mapped_column(Boolean, default=False)
    # Код для привязки записи с сайта к Telegram: t.me/<bot>?start=<code>
    link_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    client: Mapped[Client | None] = relationship(lazy="joined")
    master: Mapped[Master] = relationship(lazy="joined")
    service: Mapped[Service] = relationship(lazy="joined")


class Work(Base):
    """Фото в галерее работ на лендинге."""

    __tablename__ = "works"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int | None] = mapped_column(ForeignKey("masters.id", ondelete="SET NULL"))
    photo: Mapped[str] = mapped_column(String(255))
    caption: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), unique=True)
    # author — имя на момент отзыва. При удалении данных клиента его отзывы удаляются.
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"))
    rating: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(100), default="")
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    master: Mapped[Master] = relationship(lazy="joined")
    booking: Mapped[Booking] = relationship(lazy="joined")


class WaitlistEntry(Base):
    """Лист ожидания: клиент хочет к мастеру (или к любому) на конкретный день."""

    __tablename__ = "waitlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    client: Mapped[Client] = relationship(lazy="joined")
    service: Mapped[Service] = relationship(lazy="joined")
    master: Mapped[Master | None] = relationship(lazy="joined")
