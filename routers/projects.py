"""Project CRUD routes."""
import json
from collections import defaultdict
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import Project, Message
from models.domain import compute_phase_status, current_tab_from_phases
from services.features import FeatureQueries
from services.knowledge import KnowledgeService
from services.profiles import ProfileCommands, ProfileQueries
from services.workspace.renderer import render_workspace
from services.workspace import ProjectWorkspace

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    profiles = await ProfileQueries(db).list_profiles()
    return templates.TemplateResponse("index.html", {"request": request, "projects": projects, "profiles": profiles})


@router.post("/projects")
async def create_project(
    name: str = Form(...),
    creation_mode: str = Form("blank"),
    profile_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    project = Project(name=name)
    db.add(project)
    await db.flush()  # assigns project.id before commit so we can use it for the path

    if creation_mode == "inherit" and profile_id:
        await ProfileCommands(db).inherit_profile_into_project(project.id, profile_id)

    ws = ProjectWorkspace.create(project.name, project.id)
    project.root_path = str(ws.root)

    await db.commit()
    await db.refresh(project)
    await render_workspace(project.id, db)
    return RedirectResponse(url=f"/projects/{project.id}", status_code=303)


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_session(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        return RedirectResponse(url="/")

    msg_result = await db.execute(
        select(Message)
        .where(
            Message.project_id == project_id,
            Message.feature_id.is_(None),
            Message.archived == False,  # noqa: E712
        )
        .order_by(Message.created_at.asc())
    )
    all_messages = msg_result.scalars().all()

    # Group messages by phase tab
    history_by_tab: dict[str, list] = defaultdict(list)
    for msg in all_messages:
        tab = msg.role_tab or "ba"
        history_by_tab[tab].append(msg)

    # Compute phase status and initial active tab
    svc = KnowledgeService(db)
    snapshot = await svc.get_snapshot(project_id)
    phases = compute_phase_status(snapshot)
    initial_tab = current_tab_from_phases(phases)
    phases_json = json.dumps([p.to_dict() for p in phases])
    features = await FeatureQueries(db).list_features(project_id)

    return templates.TemplateResponse(
        "session.html",
        {
            "request": request,
            "project": project,
            "feature": None,
            "features": features,
            "history_by_tab": dict(history_by_tab),
            "phases": phases,
            "phases_json": phases_json,
            "initial_tab": initial_tab,
            "tab_keys": ["founder", "ba", "pm", "architect", "tdd", "review"],
        },
    )
