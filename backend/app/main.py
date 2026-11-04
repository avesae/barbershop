import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db, demo
from .config import get_settings
from .media import upload_dir
from .routers import admin, admin_clients, admin_masters, admin_reviews, public, tg_app
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_db()
    async with db.SessionLocal() as session:
        await seed(session)
    task = None
    if demo.enabled():
        logging.getLogger(__name__).warning("DEMO_MODE: база будет сбрасываться каждую ночь")
        await demo.ensure_demo()
        task = asyncio.create_task(demo.demo_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Fade & Blade API", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(public.router)
app.include_router(tg_app.router)
app.include_router(admin.router)
app.include_router(admin_masters.router)
app.include_router(admin_clients.router)
app.include_router(admin_reviews.router)
app.mount("/uploads", StaticFiles(directory=upload_dir()), name="uploads")

if static_dir := get_settings().static_dir:
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
