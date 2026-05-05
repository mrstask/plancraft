"""Dev Planning Studio — FastAPI entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db, migrate_db
from database import AsyncSessionLocal
from routers import projects, chat, export, docs, founder, traces, profiles, features
from routers import scaffold as scaffold_router
from services.profiles import ProfileCommands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
# SQLAlchemy is very chatty — only show warnings and above
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.projects_root.mkdir(parents=True, exist_ok=True)
    settings.profiles_root.mkdir(parents=True, exist_ok=True)
    _log.info("Projects root: %s", settings.projects_root)
    _log.info("Profiles root: %s", settings.profiles_root)
    await init_db()
    await migrate_db()
    async with AsyncSessionLocal() as db:
        await ProfileCommands(db).ensure_starter_profiles()
    yield


app = FastAPI(title="Dev Planning Studio", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(projects.router)
app.include_router(chat.router)
app.include_router(export.router)
app.include_router(docs.router)
app.include_router(founder.router)
app.include_router(traces.router)
app.include_router(profiles.router)
app.include_router(features.router)
app.include_router(scaffold_router.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
