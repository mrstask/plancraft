"""Feature contract renderer — writes specs/NNN-slug/contracts/*.md."""
from __future__ import annotations

from pathlib import Path


def render_contracts(ws, feature, contracts) -> list[Path]:
    paths: list[Path] = []
    contracts_dir = ws.feature_contracts_dir(feature)
    contracts_dir.mkdir(parents=True, exist_ok=True)

    for contract in contracts:
        path = ws.feature_contract_file(feature, contract.kind, contract.name)
        path.write_text(contract.body_md.rstrip() + "\n", encoding="utf-8")
        paths.append(path)

    return paths
