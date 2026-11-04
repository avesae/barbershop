from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .config import get_settings
from .models import Base

engine: AsyncEngine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Страховка от двойной записи на уровне PostgreSQL: у одного мастера
# не может быть двух активных записей с пересекающимся временем.
_PG_NO_OVERLAP = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'bookings_no_overlap') THEN
    ALTER TABLE bookings ADD CONSTRAINT bookings_no_overlap
      EXCLUDE USING gist (master_id WITH =, tsrange(start_at, end_at) WITH &&)
      WHERE (status = 'active');
  END IF;
END $$;
"""


async def init_db(target: AsyncEngine = engine) -> None:
    async with target.begin() as conn:
        if target.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.run_sync(Base.metadata.create_all)
        if target.dialect.name == "postgresql":
            await conn.execute(text(_PG_NO_OVERLAP))
