"""Dev Planning Studio — FastAPI entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db, migrate_db
from routers import projects, chat, export, docs

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
    _log.info("Projects root: %s", settings.projects_root)
    await init_db()
    await migrate_db()
    yield


app = FastAPI(title="Dev Planning Studio", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(projects.router)
app.include_router(chat.router)
app.include_router(export.router)
app.include_router(docs.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
