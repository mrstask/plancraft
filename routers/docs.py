"""Document tree routes — left-sidebar browsing of captured artifacts."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.knowledge import KnowledgeService
from services.knowledge.queries import ArtifactQueries
from services.workspace.renderers.constitution import render_constitution
from services.workspace.workspace import ProjectWorkspace
from roles.ba_clarifications import CATALOG_BY_ID

router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def _tree_context(project_id: str, db: AsyncSession, feature_id: str | None = None) -> dict:
    svc = KnowledgeService(db, feature_id=feature_id)
    queries = ArtifactQueries(db, feature_id=feature_id)
    project = await svc._get_project(project_id)
    epics = await svc.get_all_epics(project_id)
    stories = await svc.get_all_stories(project_id)
    components = await svc.get_all_components(project_id)
    decisions = await svc.get_all_decisions(project_id)
    contracts = await svc.get_all_interface_contracts(project_id)
    constraints = await svc.get_all_constraints(project_id)
    test_specs = await svc.get_all_test_specs(project_id)
    tasks = await svc.get_all_tasks(project_id)
    clarifications = await svc.get_all_clarification_points(project_id)
    personas = await queries.get_all_personas(project_id)
    user_flows = await queries.get_all_user_flows(project_id)
    business_rules = await queries.get_all_business_rules(project_id)
    data_entities = await queries.get_all_data_entities(project_id)
    functional_requirements = await queries.get_all_functional_requirements(project_id)
    mission = await queries.get_project_mission(project_id)
    roadmap_items = await queries.get_all_roadmap_items(project_id)
    tech_stack_entries = await queries.get_all_tech_stack_entries(project_id)
    return dict(
        project=project, epics=epics, stories=stories,
        components=components, decisions=decisions, contracts=contracts, constraints=constraints,
        test_specs=test_specs, tasks=tasks,
        clarifications=clarifications,
        personas=personas, user_flows=user_flows, business_rules=business_rules,
        data_entities=data_entities, functional_requirements=functional_requirements,
        mission=mission, roadmap_items=roadmap_items, tech_stack_entries=tech_stack_entries, feature_id=feature_id,
    )


@router.get("/projects/{project_id}/doc-tree", response_class=HTMLResponse)
async def doc_tree(
    project_id: str,
    request: Request,
    feature_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    ctx = await _tree_context(project_id, db, feature_id=feature_id)
    return templates.TemplateResponse(
        "partials/doc_tree.html",
        {"request": request, "project_id": project_id, **ctx},
    )


@router.get("/projects/{project_id}/doc-tree/{item_type}/{item_id}", response_class=HTMLResponse)
async def doc_detail(
    project_id: str,
    item_type: str,
    item_id: str,
    request: Request,
    feature_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db, feature_id=feature_id)
    item = None

    match item_type:
        case "mission":
            item = await svc.get_project_mission(project_id)
        case "roadmap-item":
            item = await svc.get_roadmap_item(project_id, item_id)
        case "tech-stack":
            item = await svc.get_tech_stack_entry(project_id, item_id)
        case "story":
            item = await svc.get_story(project_id, item_id)
        case "component":
            item = await svc.get_component(project_id, item_id)
        case "decision":
            item = await svc.get_decision(project_id, item_id)
        case "contract":
            item = await svc.get_interface_contract(project_id, item_id)
        case "clarification":
            cp = await svc.get_clarification_point(project_id, item_id)
            if cp:
                point = CATALOG_BY_ID.get(cp.point_id)
                item = {
                    "id": cp.id,
                    "point_id": cp.point_id,
                    "label": point.name if point else cp.point_id,
                    "question": point.question_to_user if point else cp.point_id,
                    "status": cp.status,
                    "answer": cp.answer or "",
                }
        case "test-spec":
            item = await svc.get_test_spec(project_id, item_id)
        case "task":
            item = await svc.get_task(project_id, item_id)

    return templates.TemplateResponse(
        "partials/doc_detail.html",
        {
            "request": request,
            "project_id": project_id,
            "item_type": item_type,
            "item": item,
            "feature_id": feature_id,
        },
    )


@router.get("/projects/{project_id}/constitution", response_class=HTMLResponse)
async def get_constitution(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    return templates.TemplateResponse(
        "partials/constitution_editor.html",
        {
            "request": request,
            "project_id": project_id,
            "constitution_md": project.constitution_md or "",
        },
    )


@router.put("/projects/{project_id}/constitution", response_class=JSONResponse)
async def update_constitution(
    project_id: str,
    constitution_md: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    queries = ArtifactQueries(db)
    project = await queries.get_project(project_id)
    project.constitution_md = constitution_md
    await db.commit()
    await db.refresh(project)

    if project.root_path:
        ws = ProjectWorkspace.from_path(project.root_path)
        render_constitution(ws, constitution_md)

    return JSONResponse({"ok": True})
