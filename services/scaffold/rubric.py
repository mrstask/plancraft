"""Evaluator rubric for the Scaffolder phase.

Checks:
1. Every component has at least one generated module under backend/src/<pkg>/
2. If test specs exist, at least one test file must exist under backend/tests/
3. Basic import sanity: generated Python files don't import non-existent siblings
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_IMPORT_RE = re.compile(r"^(?:from|import)\s+([\w.]+)", re.MULTILINE)
_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Stdlib / well-known packages that are OK to import without a local module
_KNOWN_PACKAGES = frozenset({
    "fastapi", "pydantic", "sqlalchemy", "uvicorn",
    "typing", "os", "sys", "pathlib", "asyncio", "datetime",
    "uuid", "json", "re", "abc", "dataclasses", "enum",
    "logging", "collections", "functools", "itertools",
    "contextlib", "inspect", "traceback", "io", "math",
    "pytest", "httpx", "starlette", "anyio",
})


@dataclass
class RubricResult:
    passed: bool
    score: float                               # 0..1
    missing_component_modules: list[str] = field(default_factory=list)
    missing_test_files: list[str] = field(default_factory=list)
    broken_imports: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ScaffoldRubric:
    rubric_version = "scaffold-v1"

    def check(
        self,
        impl_dir: Path,
        package_slug: str,
        component_names: list[str],
        spec_count: int,
        has_frontend: bool,
    ) -> RubricResult:
        src_dir   = impl_dir / "backend" / "src" / package_slug
        tests_dir = impl_dir / "backend" / "tests"

        existing_modules = (
            {f.stem for f in src_dir.glob("*.py") if f.stem != "__init__"}
            if src_dir.exists() else set()
        )
        existing_tests = (
            {f.stem for f in tests_dir.glob("test_*.py")}
            if tests_dir.exists() else set()
        )

        # 1. Component -> module coverage
        missing_modules: list[str] = []
        for name in component_names:
            slug = _SLUG_RE.sub("_", name.lower()).strip("_")
            # permissive: any existing module whose stem contains (or is contained by) slug
            if not any(slug in m or m in slug for m in existing_modules):
                missing_modules.append(name)

        # 2. Test file coverage
        missing_test_files: list[str] = []
        if spec_count > 0 and not existing_tests:
            missing_test_files.append(
                f"No test files found under backend/tests/ (expected >=1 for {spec_count} spec(s))"
            )

        # 3. Broken import detection
        broken_imports: list[str] = []
        if src_dir.exists():
            for py_file in src_dir.glob("*.py"):
                source = py_file.read_text(encoding="utf-8", errors="replace")
                for m in _IMPORT_RE.finditer(source):
                    top_level = m.group(1).split(".")[0]
                    if (
                        top_level
                        and top_level not in _KNOWN_PACKAGES
                        and top_level != package_slug
                        and not (src_dir / f"{top_level}.py").exists()
                        and not (src_dir / top_level / "__init__.py").exists()
                    ):
                        broken_imports.append(f"{py_file.name}: imports unknown '{top_level}'")

        issues = len(missing_modules) + len(missing_test_files) + len(broken_imports)
        checks = max(1, len(component_names) + max(spec_count, 1))
        score = max(0.0, round(1.0 - issues / checks, 2))

        notes: list[str] = []
        if src_dir.exists():
            notes.append(f"{len(existing_modules)} backend module(s) found")
        if tests_dir.exists():
            notes.append(f"{len(existing_tests)} backend test file(s) found")

        return RubricResult(
            passed=issues == 0,
            score=score,
            missing_component_modules=missing_modules,
            missing_test_files=missing_test_files,
            broken_imports=broken_imports[:10],
            notes=notes,
        )
