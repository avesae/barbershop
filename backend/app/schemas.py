from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ServiceOut(ORM):
    id: int
    name: str
    description: str
    price: int
    duration_min: int
    is_active: bool
    rebook_days: int = 28
    master_ids: list[int] = []


class MasterOut(ORM):
    id: int
    name: str
    title: str
    bio: str
    photo: str | None
    service_ids: list[int] = []


class BookingIn(BaseModel):
    service_id: int
    master_id: int
    start_at: datetime
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=5, max_length=30)
    consent: bool


class BookingCreated(BaseModel):
    id: int
    summary: str
    bot_link: str | None


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    price: int = Field(ge=0)
    duration_min: int = Field(ge=15, le=480)
    is_active: bool = True
    rebook_days: int = Field(default=28, ge=0, le=365)
    master_ids: list[int] = []


class TimeOffIn(BaseModel):
    master_id: int
    day: date
    start: time | None = None  # пусто — весь день
    end: time | None = None
    reason: str = Field(default="", max_length=100)


class TimeOffOut(ORM):
    id: int
    master_id: int
    start_at: datetime
    end_at: datetime
    reason: str


class AdminBooking(BaseModel):
    id: int
    master_id: int
    master: str
    service: str
    start_at: datetime
    end_at: datetime
    price: int
    status: str
    source: str
    client_name: str | None
    client_phone: str | None
    telegram: bool
