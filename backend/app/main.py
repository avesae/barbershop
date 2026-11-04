import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from .config import get_settings
from .routers import admin, public
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_db()
    async with db.SessionLocal() as session:
        await seed(session)
    yield


app = FastAPI(title="Fade & Blade API", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(public.router)
app.include_router(admin.router)

if static_dir := get_settings().static_dir:
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
