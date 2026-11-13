"""表生命周期状态机回归脚本（仅依赖标准库，用 ``python -I`` 运行）。

覆盖：
1. LIFE-0001 回归字段：表名称、创建日期、保留天数、归档路径、清理方式；
2. 严格顺序推进 草稿→生效中→已到期→已归档，越级/回退/人工撤销全部拒绝；
3. 每次成功推进只写一条审计事件，动作重放不产生第二条；
4. 多线程争抢同一条策略只有一个推进结果，其余读到相同终态；
5. 审计前后值与回收站 RECY-0001 的删除时间、可恢复期对得上；
6. 回收站随生命周期同步显示“到期待回收 / 已归档”；
7. 概览待处理量与列表真实状态一致。
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.store import store  # noqa: E402
from app.services.lifecycle import LifecycleService  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def events_for(policy_code: str) -> list[dict]:
    return [r for r in store.rows("audit") if r.get("来源记录") == policy_code]


def lifecycle_row(policy_code: str) -> dict:
    return next(r for r in store.rows("lifecycle") if r["策略编号"] == policy_code)


def recycle_row(table: str) -> dict:
    return next(r for r in store.rows("recycle") if r["表名称"] == table)


def main() -> int:
    svc = LifecycleService()
    store.reset()

    print("【1】LIFE-0001 回归字段")
    row = lifecycle_row("LIFE-0001")
    check("初始状态为草稿", row["status"] == "草稿")
    check("表名称 ods_order_detail", row["表名称"] == "ods_order_detail")
    check("创建日期 2026-09-01", row["创建日期"] == "2026-09-01")
    check("保留天数 90", row["保留天数"] == "90")
    check("归档路径", row["归档路径"] == "oss://dw-archive/ods_order_detail/")
    check("清理方式 先归档后删除", row["清理方式"] == "先归档后删除")
    check("策略状态展示字段与内部状态一致", row["策略状态"] == row["status"])
    check("草稿计入待处理", row["pending"] is True)

    print("【2】越级与回退全部拒绝，状态与审计不变")
    base_events = len(store.rows("audit"))
    for bad in ("删除表", "归档表"):
        entry, msg = svc.run_action(row["id"], bad)
        check(f"草稿拒绝{bad}", entry is None and lifecycle_row("LIFE-0001")["status"] == "草稿", msg)
    entry, _ = svc.run_action(row["id"], "撤销")
    check("人工撤销拒绝", entry is None)
    entry, _ = svc.run_action(row["id"], "不存在的动作")
    check("非法动作拒绝", entry is None)
    check("被拒动作不写审计", len(store.rows("audit")) == base_events)

    print("【3】顺序推进，每步唯一审计结论")
    expected = [("启用策略", "生效中"), ("删除表", "已到期"), ("归档表", "已归档")]
    for action, target in expected:
        entry, msg = svc.run_action(row["id"], action)
        check(
            f"{action} 推进到 {target}",
            entry is not None and entry["status"] == target and entry["策略状态"] == target,
            msg,
        )
        check("最后操作记录唯一动作结论", entry["最后操作"] == action)
    check("终态已归档不再计入待处理", lifecycle_row("LIFE-0001")["pending"] is False)
    evs = events_for("LIFE-0001")
    check("三次推进三条审计事件", len(evs) == 3, f"实际 {len(evs)}")
    check(
        "事件动作序列唯一且有序",
        [e["变更类型"] for e in evs] == ["启用策略", "删除表", "归档表"],
    )
    check("事件编号唯一", len({e["记录编号"] for e in evs}) == 3)

    print("【4】终态拒绝一切动作；同动作重放幂等不写第二条")
    n_after = len(events_for("LIFE-0001"))
    for action in ("启用策略", "删除表", "归档表"):
        entry, _ = svc.run_action(row["id"], action)
    check("重放后审计仍是三条", len(events_for("LIFE-0001")) == n_after)

    # 在中途状态上重放同一动作：LIFE-0003 种子处于已到期，归档表是它唯一合法动作
    svc.run_action(3, "归档表")  # 已到期 -> 已归档
    before = len(events_for("LIFE-0003"))
    entry, msg = svc.run_action(3, "归档表")
    check("同动作重放返回成功但幂等", entry is not None and "请勿重复提交" in msg, msg)
    check("重放不新增审计", len(events_for("LIFE-0003")) == before == 1)

    print("【5】旧动作名称兼容（LIFE-0002 种子为生效中，启用策略历史上已执行过）")
    check("初始无生命周期审计", len(events_for("LIFE-0002")) == 0)
    entry, msg = svc.run_action(2, "启用策略")  # 该动作历史已执行 -> 幂等重放
    check("已执行动作重放回相同终态", entry is not None and entry["status"] == "生效中" and "请勿重复提交" in msg, msg)
    check("重放不写审计", len(events_for("LIFE-0002")) == 0)
    entry, msg = svc.run_action(2, "停用")  # 旧名，等同删除表
    check("旧名「停用」映射到删除表并推进", entry is not None and entry["status"] == "已到期", msg)
    check("旧名动作写入一条审计", len(events_for("LIFE-0002")) == 1)
    entry, msg = svc.run_action(2, "清理")  # 同一语义再次调用 -> 幂等
    check("旧名「清理」重放幂等", entry is not None and entry["status"] == "已到期")
    check("旧名不产生重复事件", len(events_for("LIFE-0002")) == 1)
    entry, _ = svc.run_action(2, "启用策略")  # 已到期点启用 -> 回退越级，必须拒绝
    check("回退类越级动作仍拒绝且状态不变", entry is None and lifecycle_row("LIFE-0002")["status"] == "已到期")

    print("【6】审计前后值与回收站删除时间/可恢复期对账（取删除后、归档前的事件）")
    delete_event = next(e for e in events_for("LIFE-0001") if e["变更类型"] == "删除表")
    recy = recycle_row("ods_order_detail")
    check("回收站复用 RECY-0001 不新增记录", recy["记录编号"] == "RECY-0001")
    check("审计前值含删除时间", recy["删除时间"] in delete_event["变更前值"], delete_event["变更前值"])
    check("审计后值含可恢复期", recy["可恢复期"] in delete_event["变更后值"], delete_event["变更后值"])
    check(
        "可恢复期=删除时间+7天",
        recy["可恢复期"].startswith("2026-11-20") and recy["删除时间"].startswith("2026-11-13"),
        f"{recy['删除时间']} -> {recy['可恢复期']}",
    )

    print("【7】“到期待回收”与“已归档”两个回收站状态独立验证")
    # LIFE-0002 在【5】里刚被删除表，应处于到期待回收
    recy2 = recycle_row("dws_user_snapshot")
    check("删除后显示到期待回收", recy2["恢复状态"] == "到期待回收" and recy2["status"] == "待恢复")
    check("待回收记录计入待处理", recy2["pending"] is True)
    # LIFE-0001 在【3】里已归档，应处于已归档终态
    check("归档后回收站显示已归档", recy["恢复状态"] == "已归档" and recy["status"] == "已过期")
    check("归档写入清理时间", bool(recy["清理时间"]))
    check("归档后回收站不再计入待处理", recy["pending"] is False)

    print("【8】并发争抢：同一条策略只接受一个推进结果")
    store.reset()
    target_id = lifecycle_row("LIFE-0001")["id"]
    outcomes: list[str] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        _entry, _msg = svc.run_action(target_id, "启用策略")
        outcomes.append(_entry["status"] if _entry else "拒绝")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    final = lifecycle_row("LIFE-0001")
    check("终态唯一为生效中", final["status"] == "生效中", str(set(outcomes)))
    check("只产生一条启用审计", len(events_for("LIFE-0001")) == 1)

    print("【9】概览待处理量与列表状态一致")
    # 先把一条策略推到终态，确认终态不进 pending，再比对概览口径。
    svc.run_action(lifecycle_row("LIFE-0001")["id"], "启用策略")
    svc.run_action(lifecycle_row("LIFE-0001")["id"], "删除表")
    svc.run_action(lifecycle_row("LIFE-0001")["id"], "归档表")
    overview = store.overview()
    lc_module = next(m for m in overview["modules"] if m["name"] == "lifecycle")
    expected_pending = sum(1 for r in store.rows("lifecycle") if r["pending"])
    check("overview 待处理 = 列表 pending 计数", lc_module["pending"] == expected_pending)
    check("已归档不计入待处理", lifecycle_row("LIFE-0001")["pending"] is False)
    check("概览卡片待处理汇总包含各模块", overview["cards"][2]["label"] == "待处理")

    print(f"\n结果：通过 {PASS} 项，失败 {FAIL} 项")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
