"""Workspace renderer orchestrator.

Loads all project data from DB and writes the full docs-as-code workspace.
Called as a fire-and-forget background task after each LLM turn that modifies artifacts.
All operations are idempotent — safe to re-run at any time.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from services.export.queries import ExportDataLoader
from services.knowledge.queries import ArtifactQueries
from services.workspace.workspace import ProjectWorkspace
from services.workspace.renderers import arc42, stories, specs, tasks, c4, readme
from services.workspace.renderers import (
    adrs_split as adrs_split_renderer,
    vision_scope as vs_renderer,
    personas as personas_renderer,
    flows as flows_renderer,
    business_rules as br_renderer,
    data_model as dm_renderer,
    functional_requirements as fr_renderer,
    mission as mission_renderer,
    constitution as constitution_renderer,
    profile_metadata as profile_renderer,
    feature_spec as feature_spec_renderer,
    feature_plan as feature_plan_renderer,
    feature_tasks as feature_tasks_renderer,
    contracts as contracts_renderer,
    research as research_renderer,
    roadmap as roadmap_renderer,
    tech_stack as tech_stack_renderer,
)
from services.workspace import role_context as rc

log = logging.getLogger(__name__)


async def render_workspace(project_id: str, db: AsyncSession) -> None:
    """Render all workspace files for a project. Safe to call in the background."""
    try:
        loader = ExportDataLoader(db)
        project = await loader.get_project(project_id)

        if not project.root_path:
            log.debug("Project %s has no workspace path — skipping render", project_id)
            return

        ws = ProjectWorkspace.from_path(project.root_path)
        ws.scaffold()  # ensure dirs exist if workspace was created before this feature

        arc42_data = await loader.load_arc42_export(project_id)
        task_data = await loader.load_task_export(project_id)

        # arc42 sections
        arc42.render_all(ws, arc42_data)

        queries = ArtifactQueries(db)
        features = list(await queries.get_all_features(project_id))
        features_by_id = {feature.id: feature for feature in features}

        # per-artifact files
        adrs_split_renderer.render_split_adrs(
            ws,
            list(await queries.get_all_decisions(project_id)),
            features_by_id,
        )
        stories.render_all(ws, list(arc42_data.stories))
        specs.render_all(ws, list(arc42_data.specs))
        tasks.render_all(ws, task_data)

        # C4 model
        c4.render_c4(ws, arc42_data.project_name, list(arc42_data.components))

        # README index
        readme.render_readme(ws, arc42_data)
        constitution_renderer.render_constitution(ws, project.constitution_md or "")
        profile_renderer.render_profile_metadata(ws, project.profile_ref)

        # BA artifact files (docs/ba/)
        ba_project = await queries.get_project(project_id)
        mission_renderer.render_mission(ws, await queries.get_project_mission(project_id))
        roadmap_renderer.render_roadmap(ws, list(await queries.get_all_roadmap_items(project_id)))
        tech_stack_renderer.render_tech_stack(ws, list(await queries.get_all_tech_stack_entries(project_id)))
        vs_renderer.render_vision_scope(ws, ba_project)
        personas_renderer.render_personas(ws, list(await queries.get_all_personas(project_id)))
        flows_renderer.render_user_flows(ws, list(await queries.get_all_user_flows(project_id)))
        br_renderer.render_business_rules(ws, list(await queries.get_all_business_rules(project_id)))
        dm_renderer.render_data_model(ws, list(await queries.get_all_data_entities(project_id)))
        fr_renderer.render_functional_requirements(
            ws, list(await queries.get_all_functional_requirements(project_id))
        )

        for feature in features:
            feature_queries = ArtifactQueries(db, feature_id=feature.id)
            feature_spec_renderer.render_feature_spec(
                ws,
                feature,
                list(await feature_queries.get_all_stories(project_id)),
            )
            feature_plan_renderer.render_feature_plan(
                ws,
                feature,
                list(await queries.get_all_components(project_id)),
                list(await feature_queries.get_all_decisions(project_id)),
            )
            feature_tasks_renderer.render_feature_tasks(
                ws,
                feature,
                list(await feature_queries.get_all_tasks(project_id)),
            )
            contracts_renderer.render_contracts(
                ws,
                feature,
                list(await feature_queries.get_all_interface_contracts(project_id)),
            )
            research_renderer.render_research(
                ws,
                feature,
                list(await feature_queries.get_all_clarification_points(project_id)),
            )

        # Per-role context files for LLM prompt building
        await rc.render_all_roles(ws, project_id, db)

        log.info("Workspace rendered for project %s → %s", project_id, ws.root)

    except Exception:
        log.exception("Workspace render failed for project %s", project_id)


def schedule_render(project_id: str, db: AsyncSession) -> None:
    """Schedule a background render without blocking the caller."""
    asyncio.ensure_future(render_workspace(project_id, db))
