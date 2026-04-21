"""Profile CRUD and project save-as-profile routes."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.profiles import (
    ProfileCommands,
    ProfileQueries,
    parse_conventions_json,
    parse_tech_stack_template,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _default_constitution() -> str:
    path = Path(__file__).resolve().parent.parent / "services" / "workspace" / "templates" / "default_constitution.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _profile_view_model(profile):
    return {
        "profile": profile,
        "tech_stack_entries": parse_tech_stack_template(profile.tech_stack_template),
        "conventions": parse_conventions_json(profile.conventions_json),
        "tech_stack_json": profile.tech_stack_template or "[]",
        "conventions_json": profile.conventions_json or "{}",
    }


def _parse_json_or_raise(raw: str, *, expected: type, label: str):
    try:
        data = json.loads(raw or ("[]" if expected is list else "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON.") from exc
    if not isinstance(data, expected):
        kind = "array" if expected is list else "object"
        raise ValueError(f"{label} must be a JSON {kind}.")
    return data


@router.get("/profiles", response_class=HTMLResponse)
async def profile_index(
    request: Request,
    selected: str | None = Query(None),
    profile_ref: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    queries = ProfileQueries(db)
    profiles = await queries.list_profiles()
    selected_profile = None
    if selected:
        selected_profile = await queries.get_profile(selected)
    elif profile_ref:
        selected_profile = await queries.get_profile_by_ref(profile_ref)
    elif profiles:
        selected_profile = profiles[0]

    context = {
        "request": request,
        "profiles": profiles,
        "selected_profile": selected_profile,
        "selected_profile_vm": _profile_view_model(selected_profile) if selected_profile else None,
        "default_constitution": _default_constitution(),
        "profile_ref": profile_ref,
    }
    return templates.TemplateResponse("profiles/index.html", context)


@router.get("/profiles/preview", response_class=HTMLResponse)
async def profile_preview(
    request: Request,
    profile_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    profile = await ProfileQueries(db).get_profile(profile_id) if profile_id else None
    return templates.TemplateResponse(
        "profiles/preview.html",
        {
            "request": request,
            "profile": profile,
            "tech_stack_entries": parse_tech_stack_template(profile.tech_stack_template) if profile else [],
        },
    )


@router.get("/profiles/{profile_id}", response_class=HTMLResponse)
async def profile_detail(
    profile_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    profile = await ProfileQueries(db).get_profile(profile_id)
    if not profile:
        return RedirectResponse("/profiles", status_code=303)
    return templates.TemplateResponse(
        "profiles/detail.html",
        {
            "request": request,
            **_profile_view_model(profile),
        },
    )


@router.post("/profiles")
async def create_profile(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    try:
        profile = await ProfileCommands(db).create_profile(
            name=name,
            description=description,
            constitution_md=_default_constitution(),
            tech_stack_entries=[],
            conventions={},
        )
        return RedirectResponse(f"/profiles/{profile.id}", status_code=303)
    except ValueError as exc:
        profiles = await ProfileQueries(db).list_profiles()
        return templates.TemplateResponse(
            "profiles/index.html",
            {
                "request": request,
                "profiles": profiles,
                "selected_profile": profiles[0] if profiles else None,
                "selected_profile_vm": _profile_view_model(profiles[0]) if profiles else None,
                "default_constitution": _default_constitution(),
                "profile_ref": None,
                "error": str(exc),
            },
            status_code=400,
        )


@router.post("/profiles/{profile_id}")
async def update_profile(
    profile_id: str,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    version: str = Form("1.0.0"),
    constitution_md: str = Form(""),
    tech_stack_json: str = Form("[]"),
    conventions_json: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
):
    queries = ProfileQueries(db)
    profile = await queries.get_profile(profile_id)
    if not profile:
        return RedirectResponse("/profiles", status_code=303)

    try:
        tech_stack_entries = _parse_json_or_raise(tech_stack_json, expected=list, label="Tech stack")
        conventions = _parse_json_or_raise(conventions_json, expected=dict, label="Conventions")
        updated = await ProfileCommands(db).update_profile(
            profile_id,
            name=name,
            description=description,
            version=version,
            constitution_md=constitution_md,
            tech_stack_entries=tech_stack_entries,
            conventions=conventions,
        )
        return RedirectResponse(f"/profiles/{updated.id}", status_code=303)
    except ValueError as exc:
        return templates.TemplateResponse(
            "profiles/detail.html",
            {
                "request": request,
                "profile": profile,
                "tech_stack_entries": parse_tech_stack_template(tech_stack_json),
                "conventions": parse_conventions_json(conventions_json),
                "tech_stack_json": tech_stack_json,
                "conventions_json": conventions_json,
                "error": str(exc),
            },
            status_code=400,
        )


@router.post("/profiles/{profile_id}/duplicate")
async def duplicate_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
):
    duplicated = await ProfileCommands(db).duplicate_profile(profile_id)
    return RedirectResponse(f"/profiles/{duplicated.id}", status_code=303)


@router.post("/profiles/{profile_id}/delete")
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
):
    await ProfileCommands(db).delete_profile(profile_id)
    return RedirectResponse("/profiles", status_code=303)


@router.get("/projects/{project_id}/save-as-profile", response_class=HTMLResponse)
async def save_project_as_profile_form(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from services.knowledge import KnowledgeService

    project = await KnowledgeService(db)._get_project(project_id)
    return templates.TemplateResponse(
        "profiles/save_from_project.html",
        {
            "request": request,
            "project": project,
            "suggested_name": f"{project.name} Profile",
        },
    )


@router.post("/projects/{project_id}/save-as-profile")
async def save_project_as_profile(
    project_id: str,
    profile_name: str = Form(...),
    description: str = Form(""),
    strip_project_refs: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    profile = await ProfileCommands(db).save_profile_from_project(
        project_id,
        profile_name,
        description=description,
        strip_project_refs=bool(strip_project_refs),
    )
    return RedirectResponse(f"/profiles/{profile.id}", status_code=303)
