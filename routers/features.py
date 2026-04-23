"""Feature CRUD and feature-scoped session routes."""
from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import Feature, Message, Project
from models.domain import (
    AddInterfaceContractArgs,
    AnswerClarificationPointArgs,
    UpdateInterfaceContractArgs,
    compute_feature_phase_status,
    current_tab_from_phases,
)
from roles.ba_clarifications import CATALOG
from services.features import FeatureCommands, FeatureQueries
from services.knowledge import KnowledgeService
from services.workspace.renderer import schedule_render

router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def _feature_ba_panel_context(project_id: str, feature_id: str, request: Request, db: AsyncSession) -> dict:
    svc = KnowledgeService(db, feature_id=feature_id)
    feature = await FeatureQueries(db).get_feature(project_id, feature_id)
    clarifications = await svc.get_all_clarification_points(project_id)
    answered_ids = {item.point_id for item in clarifications}
    return {
        "request": request,
        "project_id": project_id,
        "feature": feature,
        "clarifications": clarifications,
        "available_points": [point for point in CATALOG if point.id not in answered_ids],
    }


async def _feature_architect_panel_context(project_id: str, feature_id: str, request: Request, db: AsyncSession) -> dict:
    svc = KnowledgeService(db, feature_id=feature_id)
    feature = await FeatureQueries(db).get_feature(project_id, feature_id)
    return {
        "request": request,
        "project_id": project_id,
        "feature": feature,
        "contracts": await svc.get_all_interface_contracts(project_id),
        "components": await svc.get_all_components(project_id),
    }


@router.post("/projects/{project_id}/features")
async def create_feature(
    project_id: str,
    title: str = Form(...),
    description: str = Form(""),
    roadmap_item_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    feature = await FeatureCommands(db).create_feature(
        project_id,
        title=title,
        description=description,
        roadmap_item_id=roadmap_item_id or None,
    )
    return RedirectResponse(f"/projects/{project_id}/features/{feature.id}", status_code=303)


@router.post("/projects/{project_id}/features/{feature_id}")
async def update_feature(
    project_id: str,
    feature_id: str,
    title: str = Form(...),
    description: str = Form(""),
    status: str = Form("drafting"),
    roadmap_item_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    await FeatureCommands(db).update_feature(
        project_id,
        feature_id,
        title=title,
        description=description,
        status=status,
        roadmap_item_id=roadmap_item_id or None,
    )
    return RedirectResponse(f"/projects/{project_id}/features/{feature_id}", status_code=303)


@router.get("/projects/{project_id}/features/{feature_id}")
async def feature_session(
    project_id: str,
    feature_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    feature = await FeatureQueries(db).get_feature(project_id, feature_id)
    if not project or not feature:
        return RedirectResponse("/", status_code=303)

    msg_result = await db.execute(
        select(Message)
        .where(
            Message.project_id == project_id,
            Message.feature_id == feature_id,
            Message.archived == False,  # noqa: E712
        )
        .order_by(Message.created_at.asc())
    )
    all_messages = msg_result.scalars().all()

    history_by_tab: dict[str, list] = defaultdict(list)
    for msg in all_messages:
        tab = msg.role_tab or "ba"
        history_by_tab[tab].append(msg)

    svc = KnowledgeService(db, feature_id=feature_id)
    snapshot = await svc.get_snapshot(project_id)
    phases = compute_feature_phase_status(snapshot)
    initial_tab = current_tab_from_phases(phases)
    phases_json = json.dumps([p.to_dict() for p in phases])
    features = await FeatureQueries(db).list_features(project_id)

    return templates.TemplateResponse(
        "session.html",
        {
            "request": request,
            "project": project,
            "feature": feature,
            "features": features,
            "history_by_tab": dict(history_by_tab),
            "phases": phases,
            "phases_json": phases_json,
            "initial_tab": initial_tab,
            "tab_keys": ["ba", "architect", "tdd", "review"],
        },
    )


@router.get("/projects/{project_id}/features/{feature_id}/ba-panel", response_class=HTMLResponse)
async def feature_ba_panel(
    project_id: str,
    feature_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse(
        "partials/feature_ba_panel.html",
        await _feature_ba_panel_context(project_id, feature_id, request, db),
    )


@router.patch("/projects/{project_id}/features/{feature_id}/clarifications/{point_id}", response_class=HTMLResponse)
async def update_feature_clarification(
    project_id: str,
    feature_id: str,
    point_id: str,
    request: Request,
    answer: str = Form(default=""),
    status: str = Form(default="answered"),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db, feature_id=feature_id)
    await svc.answer_clarification_point(
        project_id,
        AnswerClarificationPointArgs(point_id=point_id, answer=answer, status=status),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/feature_ba_panel.html",
        await _feature_ba_panel_context(project_id, feature_id, request, db),
    )


@router.get("/projects/{project_id}/features/{feature_id}/architect-panel", response_class=HTMLResponse)
async def feature_architect_panel(
    project_id: str,
    feature_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    return templates.TemplateResponse(
        "partials/feature_architect_panel.html",
        await _feature_architect_panel_context(project_id, feature_id, request, db),
    )


@router.post("/projects/{project_id}/features/{feature_id}/contracts", response_class=HTMLResponse)
async def create_feature_contract(
    project_id: str,
    feature_id: str,
    request: Request,
    component_id: str = Form(...),
    kind: str = Form(...),
    name: str = Form(...),
    body_md: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db, feature_id=feature_id)
    await svc.add_interface_contract(
        project_id,
        AddInterfaceContractArgs(component_id=component_id, kind=kind, name=name, body_md=body_md),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/feature_architect_panel.html",
        await _feature_architect_panel_context(project_id, feature_id, request, db),
    )


@router.patch("/projects/{project_id}/features/{feature_id}/contracts/{contract_id}", response_class=HTMLResponse)
async def update_feature_contract(
    project_id: str,
    feature_id: str,
    contract_id: str,
    request: Request,
    component_id: str = Form(...),
    kind: str = Form(...),
    name: str = Form(...),
    body_md: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db, feature_id=feature_id)
    await svc.update_interface_contract(
        project_id,
        UpdateInterfaceContractArgs(
            contract_id=contract_id,
            component_id=component_id,
            kind=kind,
            name=name,
            body_md=body_md,
        ),
    )
    schedule_render(project_id, db)
    return templates.TemplateResponse(
        "partials/feature_architect_panel.html",
        await _feature_architect_panel_context(project_id, feature_id, request, db),
    )
