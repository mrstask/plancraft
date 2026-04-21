"""ProjectWorkspace — resolves and scaffolds a project's filesystem tree."""
import re
import uuid
from pathlib import Path

from config import settings


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")


class ProjectWorkspace:
    """Encapsulates all path logic for a single project's workspace directory."""

    # Sub-directories created on scaffold
    _DIRS = [
        "product",
        "specs",
        "docs/arc42",
        "docs/adr",
        "docs/stories",
        "docs/ba",
        "docs/c4",
        "docs/diagrams",
        "tests/specs",
        "tasks",
        ".plancraft/role-context",
        ".plancraft",
    ]

    def __init__(self, workspace_path: Path) -> None:
        self.root = workspace_path

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, project_name: str, project_id: str) -> "ProjectWorkspace":
        """Create a new workspace directory for a freshly created project."""
        slug = _slugify(project_name)
        short_id = project_id.replace("-", "")[:8]
        dir_name = f"{slug}-{short_id}"
        root = settings.projects_root / dir_name
        ws = cls(root)
        ws.scaffold()
        return ws

    @classmethod
    def from_path(cls, workspace_path: str | Path) -> "ProjectWorkspace":
        """Reconstitute a workspace from a stored absolute path."""
        return cls(Path(workspace_path))

    # ------------------------------------------------------------------
    # Scaffold
    # ------------------------------------------------------------------

    def scaffold(self) -> None:
        """Create all standard sub-directories (idempotent)."""
        for rel in self._DIRS:
            (self.root / rel).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Well-known paths
    # ------------------------------------------------------------------

    @property
    def readme(self) -> Path:
        return self.root / "README.md"

    @property
    def arc42_dir(self) -> Path:
        return self.root / "docs" / "arc42"

    def arc42_section(self, n: int, name: str) -> Path:
        return self.arc42_dir / f"{n:02d}_{name}.md"

    @property
    def adr_dir(self) -> Path:
        return self.root / "docs" / "adr"

    def adr_file(self, n: int, title: str) -> Path:
        slug = _slugify(title)
        return self.adr_dir / f"{n:04d}-{slug}.md"

    @property
    def stories_dir(self) -> Path:
        return self.root / "docs" / "stories"

    def story_file(self, n: int) -> Path:
        return self.stories_dir / f"US-{n:03d}.md"

    @property
    def ba_dir(self) -> Path:
        return self.root / "docs" / "ba"

    def ba_file(self, name: str) -> Path:
        return self.ba_dir / name

    @property
    def c4_dir(self) -> Path:
        return self.root / "docs" / "c4"

    @property
    def product_dir(self) -> Path:
        return self.root / "product"

    @property
    def mission_file(self) -> Path:
        return self.product_dir / "mission.md"

    @property
    def roadmap_file(self) -> Path:
        return self.product_dir / "roadmap.md"

    @property
    def tech_stack_file(self) -> Path:
        return self.product_dir / "tech-stack.md"

    @property
    def c4_workspace(self) -> Path:
        return self.c4_dir / "workspace.dsl"

    @property
    def diagrams_dir(self) -> Path:
        return self.root / "docs" / "diagrams"

    @property
    def specs_dir(self) -> Path:
        return self.root / "tests" / "specs"

    @property
    def feature_specs_dir(self) -> Path:
        return self.root / "specs"

    def feature_dir(self, feature) -> Path:
        return self.feature_specs_dir / f"{feature.ordinal:03d}-{feature.slug}"

    def feature_file(self, feature, name: str) -> Path:
        return self.feature_dir(feature) / name

    def feature_contracts_dir(self, feature) -> Path:
        return self.feature_dir(feature) / "contracts"

    def feature_contract_file(self, feature, kind: str, name: str) -> Path:
        return self.feature_contracts_dir(feature) / f"{_slugify(kind)}-{_slugify(name)}.md"

    def feature_adr_dir(self, feature) -> Path:
        return self.feature_dir(feature) / "adrs"

    def feature_adr_file(self, feature, n: int, title: str) -> Path:
        return self.feature_adr_dir(feature) / f"{n:04d}-{_slugify(title)}.md"

    def feature_research_file(self, feature) -> Path:
        return self.feature_dir(feature) / "research.md"

    def spec_file(self, n: int) -> Path:
        return self.specs_dir / f"SPEC-{n:03d}.md"

    @property
    def tasks_dir(self) -> Path:
        return self.root / "tasks"

    @property
    def tasks_json(self) -> Path:
        return self.tasks_dir / "tasks.json"

    def task_file(self, n: int) -> Path:
        return self.tasks_dir / f"TASK-{n:03d}.md"

    @property
    def plancraft_dir(self) -> Path:
        return self.root / ".plancraft"

    def role_context_file(self, role: str) -> Path:
        return self.plancraft_dir / "role-context" / f"{role}.md"

    @property
    def constitution_file(self) -> Path:
        return self.plancraft_dir / "constitution.md"

    @property
    def snapshot_file(self) -> Path:
        return self.plancraft_dir / "snapshot.json"

    @property
    def profile_file(self) -> Path:
        return self.plancraft_dir / "profile.yml"
