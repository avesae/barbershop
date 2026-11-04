from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./barbershop.db"

    bot_token: str = ""
    bot_username: str = ""
    # Чат владельца: сюда приходят уведомления о новых записях.
    admin_chat_id: str = ""

    admin_user: str = "admin"
    admin_password: str = "admin"

    shop_name: str = "Fade & Blade"
    shop_address: str = "Москва, ул. Покровка, 17"
    shop_phone: str = "+7 (495) 000-00-00"
    shop_tz: str = "Europe/Moscow"
    site_url: str = "http://localhost"

    slot_step_min: int = 30
    booking_days_ahead: int = 14
    # Минимум минут между «сейчас» и началом записи.
    min_lead_min: int = 60
    reminder_check_sec: int = 60

    # Загруженные фото мастеров и работ.
    upload_dir: str = "./uploads"

    # Только для локального запуска без Docker: API сам раздаёт собранную статику.
    static_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
