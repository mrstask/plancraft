"""Validator registry — maps target name to its validator (if any)."""
from __future__ import annotations

from services.export.targets.base import BuildResult

from .arc42_validator import Arc42Validator

_VALIDATORS = {
    "arc42": Arc42Validator(),
}


def run_validator(target_name: str, result: BuildResult) -> BuildResult:
    """Run the target's validator (if registered) and update result in place."""
    validator = _VALIDATORS.get(target_name)
    if validator is None:
        result.schema_valid = True
        result.schema_errors = []
        return result

    errors = validator.validate(result)
    result.schema_valid = len(errors) == 0
    result.schema_errors = errors
    return result


__all__ = ["run_validator"]
