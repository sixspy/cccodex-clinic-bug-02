"""换版兼容读轨审计：汇总落点台账与切流账册两侧引用。"""
from __future__ import annotations

from app.services.compat_cut import dashboard, list_landings, snapshot
from app.services.compat_cut_cutover import board as cutover_board


def audit_list(db_path: str | None = None) -> list[dict]:
    return list_landings(db_path)


def audit_summary(db_path: str | None = None) -> dict:
    snap = snapshot(db_path)
    return {
        "title": "换版兼容审计",
        "fate": "cutover_book",
        "aligned": snap["aligned"],
        "reason": snap["reason"],
        "field_version": snap["field_version"],
        "pinned_version": snap["pinned_version"],
        "landing_id": snap["landing_id"],
        "landings": audit_list(db_path),
        "cutover": cutover_board(db_path),
        "header": dashboard(db_path),
    }
