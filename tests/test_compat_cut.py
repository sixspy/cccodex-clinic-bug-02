"""换版兼容假绿回归：落点入表、指纹/字段版号对照、错列灌批拦截、争用加锁。

本文件先于实现落笔（红测）。运行方式：python -m pytest tests/test_compat_cut.py -q
"""
from __future__ import annotations

import importlib
import json
import threading

import pytest

from app.db import get_db
from app.services import backfill, compat_cut, protocols, qc, visits
from app.services.errors import ServiceError


def _active(db_path: str) -> dict:
    items = protocols.list_protocols(db_path=db_path, status="生效")
    assert items, "种子应存在生效方案"
    return items[0]


def _clear_landings(db_path: str) -> None:
    with get_db(db_path) as conn:
        conn.execute("DELETE FROM compat_cut_landings")
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('compat_cut_panel_chip', '字段版旧')"
        )


def _gap_batch(db_path: str) -> dict:
    return next(b for b in visits.list_batches(db_path) if b["status"] == "采集中")


# ---------------------------------------------------------------------------
# 落点入表 / 种子健康态
# ---------------------------------------------------------------------------


def test_seed_creates_landing_row_in_business_table(db_path):
    rows = compat_cut.list_landings(db_path)
    assert rows, "换版兼容落点必须先入表"
    latest = compat_cut.latest_landing(db_path)
    assert latest is not None
    proto = _active(db_path)
    assert latest["field_version"] == proto["version"]
    assert latest["fingerprint"]
    assert latest["read_track"] == "cutover_book"
    assert int(latest["reject_refresh"]) == 1

    snap = compat_cut.snapshot(db_path)
    assert snap["aligned"] is True
    assert snap["landing_id"] == latest["id"]
    assert snap["panel_pack_mismatch"] is False
    assert snap["field_version"] == proto["version"]
    assert snap["pinned_version"] == proto["version"]


# ---------------------------------------------------------------------------
# 仅亮徽标、缺落点行 -> 驳回并拦截错列灌批
# ---------------------------------------------------------------------------


def test_painted_chip_without_landing_is_rejected_and_blocks_injection(db_path):
    _clear_landings(db_path)
    compat_cut.paint_ok(db_path)

    snap = compat_cut.snapshot(db_path)
    assert snap["panel_chip"] == "兼容已亮"          # 徽标独亮
    assert snap["truth"] == "字段版旧"               # 真值仍是旧版
    assert snap["aligned"] is False
    assert snap["panel_pack_mismatch"] is True
    assert snap["landing_id"] == 0
    assert "落点" in snap["reason"]

    assert compat_cut.gate_allows_pipeline(db_path) is False
    with pytest.raises(ServiceError):
        compat_cut.require_pack_or_raise(db_path)

    batch = _gap_batch(db_path)
    with pytest.raises(ServiceError):
        visits.mock_crawl(batch["id"], count=1, db_path=db_path)
    with pytest.raises(ServiceError):
        qc.scan_batch(batch["id"], db_path=db_path)
    with pytest.raises(ServiceError):
        backfill.enqueue_gaps_for_batch(batch["id"], db_path=db_path)


# ---------------------------------------------------------------------------
# 指纹拧花 -> 必须判失败（不得放行）
# ---------------------------------------------------------------------------


def test_fingerprint_mismatch_is_rejected_and_blocks_pipeline(db_path):
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE compat_cut_landings SET fingerprint='deadbeef' WHERE status='landed'"
        )

    snap = compat_cut.snapshot(db_path)
    assert snap["aligned"] is False
    assert "指纹" in snap["reason"]
    assert compat_cut.gate_allows_pipeline(db_path) is False
    with pytest.raises(ServiceError):
        compat_cut.require_pack_or_raise(db_path)

    batch = _gap_batch(db_path)
    with pytest.raises(ServiceError):
        visits.mock_crawl(batch["id"], count=1, db_path=db_path)


# ---------------------------------------------------------------------------
# 字段版号漂移 -> 先挡错列灌批，再落台后可恢复
# ---------------------------------------------------------------------------


def test_field_version_drift_blocks_injection_until_relaunch(db_path):
    pinned = _active(db_path)
    new_proto = protocols.create_protocol(
        "换版随访方案丙",
        version="1.1",
        required_fields=[
            "subject_key", "visit_code", "visit_date", "investigator",
            "weight_kg", "lab_code",
        ],
        visit_codes=["V1", "V2", "V3", "EOT"],
        note="换版测试",
        db_path=db_path,
    )
    protocols.set_status(new_proto["id"], "生效", db_path=db_path)

    snap = compat_cut.snapshot(db_path)
    assert snap["field_version"] == "1.1"
    assert snap["pinned_version"] == pinned["version"]
    assert snap["aligned"] is False
    assert "字段版号" in snap["reason"]
    assert compat_cut.gate_allows_pipeline(db_path) is False

    batch = _gap_batch(db_path)
    with pytest.raises(ServiceError):
        visits.add_visit_row(
            batch["id"],
            "DRIFT-01",
            "V1",
            payload=json.dumps(
                {
                    "visit_date": "2026-11-20",
                    "investigator": "王医生",
                    "weight_kg": 60,
                    "lab_code": "L-1",
                },
                ensure_ascii=False,
            ),
            db_path=db_path,
        )

    # 落台钉住新字段版号后恢复
    relaunched = compat_cut.commit_action({"note": "换版落台"}, db_path)
    assert relaunched["landing_id"] > 0
    assert compat_cut.snapshot(db_path)["aligned"] is True
    ok = visits.add_visit_row(
        batch["id"],
        "DRIFT-02",
        "V1",
        payload=json.dumps(
            {
                "visit_date": "2026-11-20",
                "investigator": "王医生",
                "weight_kg": 60,
                "lab_code": "L-2",
            },
            ensure_ascii=False,
        ),
        db_path=db_path,
    )
    assert ok["quality"] == "合格"


# ---------------------------------------------------------------------------
# 提交即刻写完入库、幂等、且只有一行 landed
# ---------------------------------------------------------------------------


def test_commit_writes_landing_atomically_and_is_idempotent(db_path):
    _clear_landings(db_path)
    first = compat_cut.commit_action({"note": "落台"}, db_path)
    assert first["landing_id"] > 0
    assert first["aligned"] is True

    second = compat_cut.commit_action({"note": "重复落台"}, db_path)
    assert second["landing_id"] == first["landing_id"]

    landed = [x for x in compat_cut.list_landings(db_path) if x["status"] == "landed"]
    assert len(landed) == 1
    assert landed[0]["fingerprint"] == compat_cut.snapshot(db_path)["fingerprint"]
    assert compat_cut.snapshot(db_path)["aligned"] is True


def test_commit_failure_is_explained(db_path):
    with pytest.raises(ServiceError) as exc:
        compat_cut.commit_action({"fingerprint": "bogus"}, db_path)
    assert "指纹" in str(exc.value)
    # 失败不留下半截落点
    assert compat_cut.snapshot(db_path)["aligned"] is True


# ---------------------------------------------------------------------------
# 争用加锁：并发落台不得双成功踩掉钉点
# ---------------------------------------------------------------------------


def test_concurrent_commits_do_not_double_land_or_stomp(db_path):
    _clear_landings(db_path)
    workers = 4
    barrier = threading.Barrier(workers)
    results: list[dict] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            results.append(compat_cut.commit_action({"note": "并发落台"}, db_path))
        except Exception as exc:  # noqa: BLE001 - 收集任意争用异常
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    landed = [x for x in compat_cut.list_landings(db_path) if x["status"] == "landed"]
    assert len(landed) == 1, "同一时刻只允许一个 landed 落点"
    assert results, "至少一个写入方必须成功"
    assert {r["landing_id"] for r in results} == {landed[0]["id"]}
    assert compat_cut.snapshot(db_path)["aligned"] is True


# ---------------------------------------------------------------------------
# 未选边脚手架必须清掉（本题选甲路：物化包/切流账册）
# ---------------------------------------------------------------------------


def test_unselected_dualwrite_scaffolding_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.services.compat_cut_dualwrite")


def test_no_active_protocol_does_not_crash_and_blocks(db_path):
    for p in protocols.list_protocols(db_path):
        if p["status"] == "生效":
            protocols.set_status(p["id"], "废止", db_path=db_path)

    snap = compat_cut.snapshot(db_path)
    assert snap["aligned"] is False
    assert "生效方案" in snap["reason"]
    assert compat_cut.gate_allows_pipeline(db_path) is False
    with pytest.raises(ServiceError):
        compat_cut.commit_action({"note": "无方案落台"}, db_path)


# ---------------------------------------------------------------------------
# 页面所需口径：徽标 / 字段版号 / 落点行次
# ---------------------------------------------------------------------------


def test_dashboard_exposes_badge_field_version_and_landing_row(db_path):
    dash = compat_cut.dashboard(db_path)
    assert dash["chip"] in ("兼容已亮", "字段版旧")
    assert dash["field_version"]
    assert dash["landing_id"] > 0
    assert isinstance(dash["landings"], list) and dash["landings"]
    assert "aligned" in dash
    assert "reason" in dash
