"""Document tree routes — left-sidebar browsing of captured artifacts."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.knowledge import KnowledgeService

router = APIRouter()
templates = Jinja2Templates(directory="templates")


async def _tree_context(project_id: str, db: AsyncSession) -> dict:
    svc = KnowledgeService(db)
    project   = await svc._get_project(project_id)
    epics     = await svc.get_all_epics(project_id)
    stories   = await svc.get_all_stories(project_id)
    components= await svc.get_all_components(project_id)
    decisions = await svc.get_all_decisions(project_id)
    constraints = await svc.get_all_constraints(project_id)
    test_specs= await svc.get_all_test_specs(project_id)
    tasks     = await svc.get_all_tasks(project_id)
    return dict(
        project=project, epics=epics, stories=stories,
        components=components, decisions=decisions, constraints=constraints,
        test_specs=test_specs, tasks=tasks,
    )


@router.get("/projects/{project_id}/doc-tree", response_class=HTMLResponse)
async def doc_tree(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ctx = await _tree_context(project_id, db)
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
    db: AsyncSession = Depends(get_db),
):
    svc = KnowledgeService(db)
    item = None

    match item_type:
        case "story":     item = await svc.get_story(item_id)
        case "component": item = await svc.get_component(item_id)
        case "decision":  item = await svc.get_decision(item_id)
        case "test-spec": item = await svc.get_test_spec(item_id)
        case "task":      item = await svc.get_task(item_id)

    return templates.TemplateResponse(
        "partials/doc_detail.html",
        {
            "request": request,
            "project_id": project_id,
            "item_type": item_type,
            "item": item,
        },
    )
