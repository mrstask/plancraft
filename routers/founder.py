"""Founder artifact routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.domain import (
    AddRoadmapItemArgs,
    AddTechStackEntryArgs,
    SetProjectMissionArgs,
    UpdateRoadmapItemArgs,
    UpdateTechStackEntryArgs,
)
from services.knowledge import KnowledgeService
from services.workspace.renderer import schedule_render

router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def _panel_context(project_id: str, request: Request, db: AsyncSession) -> dict:
    svc = KnowledgeService(db)
    project = await svc._get_project(project_id)
    mission = await svc.get_project_mission(project_id)
    roadmap_items = await svc.get_all_roadmap_items(project_id)
    tech_stack_entries = await svc.get_all_tech_stack_entries(project_id)
    stories = await svc.get_all_stories(project_id)
    flows = await svc.get_all_user_flows(project_id)
    components = await svc.get_all_components(project_id)

    has_founder_artifacts = bool(mission or roadmap_items or tech_stack_entries)
    legacy_founder_pending = (
        not has_founder_artifacts
        and bool(
            project.description
            or project.business_goals
            or stories
            or flows
            or components
        )
    )

    return {
        "request": request,
        "project_id": project_id,
        "mission": mission,
        "roadmap_items": roadmap_items,
        "tech_stack_entries": tech_stack_entries,
        "legacy_founder_pending": legacy_founder_pending,
    }


def _bool_from_form(value: str | None) -> bool:
    return value in {"on", "true", "1", "yes"}


@router.get("/projects/{project_id}/founder/panel", response_class=HTMLResponse)
async def founder_panel(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )


@router.patch("/projects/{project_id}/founder/mission", response_class=HTMLResponse)
async def update_mission(
    project_id: str,
    request: Request,
    statement: str = Form(default=""),
    target_users: str = Form(default=""),
    problem: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    await svc.set_project_mission(
        project_id,
        SetProjectMissionArgs(
            statement=statement,
            target_users=target_users,
            problem=problem,
        ),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )


@router.post("/projects/{project_id}/founder/roadmap-items", response_class=HTMLResponse)
async def create_roadmap_item(
    project_id: str,
    request: Request,
    title: str = Form(default=""),
    description: str = Form(default=""),
    ordinal: int | None = Form(default=None),
    mvp: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    await svc.add_roadmap_item(
        project_id,
        AddRoadmapItemArgs(
            title=title,
            description=description,
            ordinal=ordinal,
            mvp=_bool_from_form(mvp),
        ),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )


@router.patch("/projects/{project_id}/founder/roadmap-items/{item_id}", response_class=HTMLResponse)
async def update_roadmap_item(
    project_id: str,
    item_id: str,
    request: Request,
    title: str = Form(default=""),
    description: str = Form(default=""),
    ordinal: int | None = Form(default=None),
    mvp: str | None = Form(default=None),
    linked_epic_id: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    await svc.update_roadmap_item(
        project_id,
        UpdateRoadmapItemArgs(
            item_id=item_id,
            title=title,
            description=description,
            ordinal=ordinal,
            mvp=_bool_from_form(mvp),
            linked_epic_id=linked_epic_id,
        ),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )


@router.post("/projects/{project_id}/founder/tech-stack-entries", response_class=HTMLResponse)
async def create_tech_stack_entry(
    project_id: str,
    request: Request,
    layer: str = Form(default=""),
    choice: str = Form(default=""),
    rationale: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    await svc.add_tech_stack_entry(
        project_id,
        AddTechStackEntryArgs(layer=layer, choice=choice, rationale=rationale),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )


@router.patch("/projects/{project_id}/founder/tech-stack-entries/{entry_id}", response_class=HTMLResponse)
async def update_tech_stack_entry(
    project_id: str,
    entry_id: str,
    request: Request,
    layer: str = Form(default=""),
    choice: str = Form(default=""),
    rationale: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    await svc.update_tech_stack_entry(
        project_id,
        UpdateTechStackEntryArgs(
            entry_id=entry_id,
            layer=layer,
            choice=choice,
            rationale=rationale,
        ),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )


@router.post("/projects/{project_id}/founder/seed", response_class=HTMLResponse)
async def seed_founder(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    await svc.seed_founder_from_existing_project(project_id)
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )


@router.post("/projects/{project_id}/founder/manual", response_class=HTMLResponse)
async def scaffold_manual_founder(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    await svc.scaffold_founder_manual_entry(project_id)
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/founder_panel.html",
        await _panel_context(project_id, request, db),
    )
