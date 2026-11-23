"""换版兼容 · 甲路（物化包钉定 / 切流账册收口）。

读侧只认 ``compat_cut_landings`` 中唯一的 ``landed`` 行：字段版号、指纹、
读轨与拒回刷标记都必须与该行一致。旧编号/旧指纹、只亮徽标而不落表、
字段版号漂移三种情形一律判未对齐，并据此挡掉错列灌批。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from app.db import get_db
from app.services.errors import ServiceError

_SLUG = "compat_cut"
_OK = "兼容已亮"
_BAD = "字段版旧"
_TITLE = "换版兼容"
_CUTOVER = "cutover_book"


def _meta_get(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        (key, value),
    )


def _current_protocol(conn) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM protocols WHERE status='生效' ORDER BY id LIMIT 1"
    ).fetchone()


def _protocol_lists(row) -> tuple[list[str], list[str]]:
    try:
        fields = json.loads(row["required_fields"] or "[]")
    except (json.JSONDecodeError, TypeError):
        fields = []
    try:
        visits = json.loads(row["visit_codes"] or "[]")
    except (json.JSONDecodeError, TypeError):
        visits = []
    fields = [str(x).strip() for x in fields if str(x).strip()] if isinstance(fields, list) else []
    visits = [str(x).strip() for x in visits if str(x).strip()] if isinstance(visits, list) else []
    return fields, visits


def compute_fingerprint(version: str, fields: list[str], visits: list[str]) -> str:
    """字段版号 + 必填字段 + 访视编码 的稳定指纹。"""
    payload = json.dumps(
        {
            "version": str(version or ""),
            "fields": sorted(fields),
            "visits": sorted(visits),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_identity(conn) -> dict | None:
    proto = _current_protocol(conn)
    if not proto:
        return None
    fields, visits = _protocol_lists(proto)
    return {
        "protocol_id": proto["id"],
        "version": str(proto["version"] or ""),
        "fingerprint": compute_fingerprint(proto["version"], fields, visits),
        "fields": fields,
        "visits": visits,
    }


def list_landings(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM compat_cut_landings
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def latest_landing(db_path: str | None = None) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM compat_cut_landings
            WHERE status='landed'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None


def _landing_eval(conn) -> dict:
    """读侧唯一判定入口：对照落点行、当刻方案与徽标。"""
    chip = _meta_get(conn, f"{_SLUG}_panel_chip", _BAD)
    identity = current_identity(conn)
    landed_rows = conn.execute(
        "SELECT * FROM compat_cut_landings WHERE status='landed' ORDER BY id DESC"
    ).fetchall()
    landing = dict(landed_rows[0]) if landed_rows else None
    archived = conn.execute(
        "SELECT COUNT(*) AS c FROM compat_cut_landings WHERE status='archived'"
    ).fetchone()["c"]

    reason = ""
    aligned = True
    if identity is None:
        aligned = False
        reason = "无生效方案可对照字段版号"
    elif not landed_rows:
        aligned = False
        reason = "缺少换版兼容落点行（仅亮徽标不算数）"
    elif len(landed_rows) > 1:
        aligned = False
        reason = "换版兼容落点行不唯一"
    elif landing["field_version"] != identity["version"]:
        aligned = False
        reason = (
            f"字段版号漂移：落点钉住 {landing['field_version']}，"
            f"当刻生效 {identity['version']}"
        )
    elif landing["fingerprint"] != identity["fingerprint"]:
        aligned = False
        reason = "换版兼容指纹拧花：落点指纹与当刻字段口径不符"
    elif landing["read_track"] != _CUTOVER:
        aligned = False
        reason = f"读轨未收口到 {_CUTOVER}"
    elif int(landing["reject_refresh"]) != 1:
        aligned = False
        reason = "读侧未拒回刷"
    elif chip != _OK:
        aligned = False
        reason = "兼容徽标非亮，读侧口径不一致"

    return {
        "chip": chip,
        "aligned": aligned,
        "reason": reason,
        "identity": identity,
        "landing": landing,
        "landing_count": len(landed_rows),
        "archive_count": archived,
    }


def snapshot(db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        ev = _landing_eval(conn)
    identity = ev["identity"] or {}
    landing = ev["landing"] or {}
    return {
        "title": _TITLE,
        "panel_chip": ev["chip"],
        "truth": _OK if ev["aligned"] else _BAD,
        "aligned": ev["aligned"],
        "reason": ev["reason"],
        "landing_id": int(landing.get("id") or 0),
        "field_version": identity.get("version", ""),
        "pinned_version": landing.get("field_version", ""),
        "fingerprint": identity.get("fingerprint", ""),
        "pinned_fingerprint": landing.get("fingerprint", ""),
        "read_track": landing.get("read_track", ""),
        "reject_refresh": bool(int(landing.get("reject_refresh") or 0)),
        "cutover_fp": landing.get("fingerprint", ""),
        "archive_count": ev["archive_count"],
        "landing_count": ev["landing_count"],
        "panel_pack_mismatch": ev["chip"] == _OK and not ev["aligned"],
    }


def panel_chip(db_path: str | None = None) -> str:
    with get_db(db_path) as conn:
        return _meta_get(conn, f"{_SLUG}_panel_chip", _BAD)


def truth_flag(db_path: str | None = None) -> str:
    with get_db(db_path) as conn:
        return _OK if _landing_eval(conn)["aligned"] else _BAD


def active_read_ref(db_path: str | None = None) -> str:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT read_track FROM compat_cut_landings "
            "WHERE status='landed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["read_track"] if row else ""


def cutover_fp(db_path: str | None = None) -> str:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT fingerprint FROM compat_cut_landings "
            "WHERE status='landed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["fingerprint"] if row else ""


def reject_refresh(db_path: str | None = None) -> bool:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT reject_refresh FROM compat_cut_landings "
            "WHERE status='landed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return bool(row and int(row["reject_refresh"]) == 1)


def paint_ok(db_path: str | None = None) -> str:
    """只改徽标、不落表——读侧仍按落点行判真值，属于被拦截的假绿情形。"""
    with get_db(db_path) as conn:
        _meta_set(conn, f"{_SLUG}_panel_chip", _OK)
        _meta_set(conn, f"{_SLUG}_display_only", "1")
    return _OK


def bootstrap_landing(conn) -> dict | None:
    """种子/首启：按当刻生效方案钉一行落点（调用方事务内），幂等。"""
    identity = current_identity(conn)
    if identity is None:
        return None
    existing = conn.execute(
        "SELECT * FROM compat_cut_landings WHERE status='landed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if existing and existing["fingerprint"] == identity["fingerprint"]:
        _meta_set(conn, f"{_SLUG}_panel_chip", _OK)
        return dict(existing)
    conn.execute("UPDATE compat_cut_landings SET status='archived' WHERE status='landed'")
    cur = conn.execute(
        """
        INSERT INTO compat_cut_landings(
          note, field_version, fingerprint, read_track, reject_refresh, status
        ) VALUES (?, ?, ?, ?, 1, 'landed')
        """,
        ("种子落点", identity["version"], identity["fingerprint"], _CUTOVER),
    )
    _meta_set(conn, f"{_SLUG}_panel_chip", _OK)
    _meta_set(conn, f"{_SLUG}_truth", _OK)
    return {
        "id": cur.lastrowid,
        "field_version": identity["version"],
        "fingerprint": identity["fingerprint"],
        "read_track": _CUTOVER,
        "reject_refresh": 1,
        "status": "landed",
    }


def commit_action(payload: dict | None = None, db_path: str | None = None) -> dict:
    """提交即刻写完落点入库；同一当刻口径幂等，争用写入只留一行 landed。"""
    payload = payload or {}
    requested_fp = str(payload.get("fingerprint") or "").strip()

    with get_db(db_path) as conn:
        # 序列化争用写入，避免两侧同时落台互相踩掉钉点
        conn.execute("BEGIN IMMEDIATE")
        identity = current_identity(conn)
        if identity is None:
            raise ServiceError(f"{_TITLE}落台失败：没有生效方案可供钉住字段版号", 409)
        if requested_fp and requested_fp != identity["fingerprint"]:
            raise ServiceError(
                f"{_TITLE}落台失败：指纹与当刻字段口径不符，拒绝钉定", 409
            )

        existing = conn.execute(
            "SELECT * FROM compat_cut_landings WHERE status='landed' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if (
            existing
            and existing["fingerprint"] == identity["fingerprint"]
            and existing["field_version"] == identity["version"]
            and existing["read_track"] == _CUTOVER
            and int(existing["reject_refresh"]) == 1
        ):
            landing_id = int(existing["id"])
            _meta_set(conn, f"{_SLUG}_panel_chip", _OK)
            _meta_set(conn, f"{_SLUG}_truth", _OK)
        else:
            note = str(payload.get("note") or "换版兼容落台")[:200]
            conn.execute(
                "UPDATE compat_cut_landings SET status='archived' WHERE status='landed'"
            )
            cur = conn.execute(
                """
                INSERT INTO compat_cut_landings(
                  note, field_version, fingerprint, read_track, reject_refresh, status
                ) VALUES (?, ?, ?, ?, 1, 'landed')
                """,
                (note, identity["version"], identity["fingerprint"], _CUTOVER),
            )
            landing_id = int(cur.lastrowid)
            _meta_set(conn, f"{_SLUG}_panel_chip", _OK)
            _meta_set(conn, f"{_SLUG}_truth", _OK)
            _meta_set(conn, f"{_SLUG}_cutover_fp", identity["fingerprint"])
            _meta_set(conn, f"{_SLUG}_active_read", _CUTOVER)
            _meta_set(conn, f"{_SLUG}_reject_refresh", "1")
            _meta_set(conn, f"{_SLUG}_mode", _CUTOVER)
        _meta_set(conn, f"{_SLUG}_last_payload", str(payload)[:200])

    snap = snapshot(db_path)
    return {
        "ok": snap["aligned"],
        "title": _TITLE,
        "chip": snap["panel_chip"],
        "landing_id": landing_id,
        "field_version": snap["field_version"],
        "fingerprint": snap["fingerprint"],
        "read_track": snap["read_track"],
        "reject_refresh": snap["reject_refresh"],
        "archive_count": snap["archive_count"],
        "aligned": snap["aligned"],
        "reason": snap["reason"],
        "message": (
            f"{_TITLE}已落台，读轨收口到 {_CUTOVER}"
            if snap["aligned"]
            else f"{_TITLE}落台后仍未对齐：{snap['reason']}"
        ),
    }


def gate_allows_pipeline(db_path: str | None = None) -> bool:
    with get_db(db_path) as conn:
        return _landing_eval(conn)["aligned"]


def require_pack_or_raise(db_path: str | None = None) -> None:
    with get_db(db_path) as conn:
        ev = _landing_eval(conn)
    if not ev["aligned"]:
        raise ServiceError(
            f"{_TITLE}读轨未对齐（{ev['reason']}），已挡下错列灌批与质控补采", 409
        )


def dashboard(db_path: str | None = None) -> dict:
    snap = snapshot(db_path)
    landings = list_landings(db_path)
    return {
        "title": _TITLE,
        "label": "换版兼容落点",
        "chip": snap["panel_chip"],
        "ok_chip": _OK,
        "bad_chip": _BAD,
        "truth": snap["truth"],
        "field_version": snap["field_version"],
        "pinned_version": snap["pinned_version"],
        "landing_id": snap["landing_id"],
        "landings": landings,
        "landing_count": snap["landing_count"],
        "archive_count": snap["archive_count"],
        "fingerprint": snap["fingerprint"],
        "pinned_fingerprint": snap["pinned_fingerprint"],
        "read_track": snap["read_track"],
        "reject_refresh": snap["reject_refresh"],
        "aligned": snap["aligned"],
        "reason": snap["reason"],
        "panel_pack_mismatch": snap["panel_pack_mismatch"],
        "read_tracks": {_CUTOVER: _CUTOVER},
    }


def list_events(db_path: str | None = None) -> list[dict]:
    """落点台账（含归档）作为事件流。"""
    return list_landings(db_path)


def half_fix_display(db_path: str | None = None) -> dict:
    """半修：只亮徽标不落表。读侧照旧按落点行判真值，因此仍判未对齐。"""
    paint_ok(db_path)
    snap = snapshot(db_path)
    return {
        "panel_chip": snap["panel_chip"],
        "truth": snap["truth"],
        "active_read": snap["read_track"],
        "landing_id": snap["landing_id"],
        "aligned": snap["aligned"],
        "reason": snap["reason"],
        "half_fixed": False,
        "message": "仅亮徽标未落表，读侧仍判未对齐",
    }


def reconcile_display(db_path: str | None = None) -> dict:
    return half_fix_display(db_path)
