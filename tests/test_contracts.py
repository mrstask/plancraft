import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base
from models import db as models_db  # noqa: F401
from models.db import Component, Feature, Project
from models.domain import AddInterfaceContractArgs, UpdateInterfaceContractArgs
from roles.architect import ArchitectRole
from services.knowledge import KnowledgeService
from services.llm import get_phase_tool_names


class InterfaceContractsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_contract_crud_is_feature_scoped(self):
        async with self.session_factory() as session:
            project = Project(name="Planner")
            session.add(project)
            await session.flush()
            feature = Feature(project_id=project.id, slug="checkout", ordinal=1, title="Checkout")
            component = Component(
                project_id=project.id,
                name="Orders API",
                responsibility="Handles order creation",
                component_type="service",
            )
            session.add_all([feature, component])
            await session.commit()

            svc = KnowledgeService(session, feature_id=feature.id)
            result = await svc.add_interface_contract(
                project.id,
                AddInterfaceContractArgs(
                    component_id=component.id,
                    kind="rest",
                    name="CreateOrder",
                    body_md="# Contract: CreateOrder",
                ),
            )
            contract_id = result.split(": ", 1)[1]

            contracts = await svc.get_all_interface_contracts(project.id)
            self.assertEqual(len(contracts), 1)
            self.assertEqual(contracts[0].id, contract_id)
            self.assertEqual(contracts[0].feature_id, feature.id)

            await svc.update_interface_contract(
                project.id,
                UpdateInterfaceContractArgs(
                    contract_id=contract_id,
                    name="CreateOrderV2",
                    body_md="# Contract: CreateOrderV2",
                ),
            )
            refreshed = await svc.get_interface_contract(project.id, contract_id)
            self.assertEqual(refreshed.name, "CreateOrderV2")
            self.assertIn("CreateOrderV2", refreshed.body_md)

    async def test_architect_tooling_includes_contract_capture(self):
        tool_names = get_phase_tool_names("architect")
        self.assertIn("add_interface_contract", tool_names)

        fragment = ArchitectRole().system_prompt_fragment
        self.assertIn("add_interface_contract()", fragment)
        self.assertIn("no external interface", fragment)


if __name__ == "__main__":
    unittest.main()
