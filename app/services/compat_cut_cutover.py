"""换版兼容 · 甲路切流账册（已选边收口面）。

切流账册只负责把「落台」动作引到唯一的物化落点写入路径，
读写都以 ``compat_cut_landings`` 的 landed 行为准。
"""
from __future__ import annotations

from app.services.compat_cut import (
    commit_action,
    dashboard,
    list_landings,
    snapshot,
)

_TITLE = "换版兼容"


def append_cutover(ref_id: int, note: str, db_path: str | None = None) -> dict:
    """切流账册落台：钉住当刻字段版号与指纹，写 durable 落点行。"""
    result = commit_action(
        {"ref_id": int(ref_id or 0), "note": (note or _TITLE)[:200]},
        db_path,
    )
    result["ref_id"] = int(ref_id or 0)
    return result


def cutover_rows(db_path: str | None = None) -> list[dict]:
    snap = snapshot(db_path)
    return [
        {
            "key": f"compat_cut_landing_{row['id']}",
            "value": row["fingerprint"],
            "field_version": row["field_version"],
            "read_track": row["read_track"],
            "reject_refresh": row["reject_refresh"],
            "status": row["status"],
            "chip": snap["panel_chip"],
            "aligned": snap["aligned"],
        }
        for row in list_landings(db_path)
    ]


def board(db_path: str | None = None) -> dict:
    dash = dashboard(db_path)
    dash["cutover"] = cutover_rows(db_path)
    dash["fate"] = "cutover_book"
    return dash
