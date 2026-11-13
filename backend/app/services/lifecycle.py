"""表生命周期管理业务规则：状态流转、字段校验与筛选口径都收在这里。

状态机（只允许逐格前进，任何回退或跳级都拒绝）：

    草稿 --启用策略--> 生效中 --删除表--> 已到期 --归档表--> 已归档(终态)

历史上 ``ACTION_RULES`` 把“动作允许的前置状态”错当成“动作写入的目标状态”，
且不校验当前状态，导致草稿执行删除表会越级写成已到期、已归档再点启用策略会
退回草稿。这里改为显式的“前置状态 -> 目标状态”流转表，并在一次仓库锁内完成
读取、校验、状态写入、审计事件写入与回收站同步，保证：

* 越级/回退动作直接拒绝，状态不变、不产生审计事件；
* 同一动作重放命中幂等分支，返回成功但不写第二条事件；
* 两个请求争抢同一条策略时只有一个完成推进，另一个读到相同终态。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.store import store

MODULE = "lifecycle"
AUDIT_MODULE = "audit"
RECYCLE_MODULE = "recycle"

REQUIRED_FIELDS = ["策略编号", "表名称", "创建日期"]
STATUS_ORDER = ["草稿", "生效中", "已到期", "已归档"]
FINAL_STATUS = STATUS_ORDER[-1]

# 动作 -> (唯一合法的前置状态, 推进后的目标状态)
# 兼容旧动作名称：上线/停用/清理 是早期版本里的叫法，语义与现用动作一一对应。
ACTION_ALIASES = {
    "启用": "启用策略",
    "上线": "启用策略",
    "启用策略": "启用策略",
    "删除": "删除表",
    "停用": "删除表",
    "清理": "删除表",
    "删除表": "删除表",
    "归档": "归档表",
    "归档表": "归档表",
}
TRANSITIONS: dict[str, tuple[str, str]] = {
    "启用策略": ("草稿", "生效中"),
    "删除表": ("生效中", "已到期"),
    "归档表": ("已到期", "已归档"),
}
# 每个动作在策略上留下的“最后操作”结论（唯一，不随重放变化）。
ACTION_CONCLUSIONS = {
    "启用策略": "启用策略",
    "删除表": "删除表",
    "归档表": "归档表",
}
# 人工撤销类动作一律不开放：状态机只进不退。
REVOKE_ACTIONS = {"撤销", "人工撤销", "回退", "撤回", "作废"}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class LifecycleService:
    # ------------------------------------------------------------------ 查询
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("策略编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ------------------------------------------------------------------ 登记
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 选填字段缺省时给空串，避免列表渲染出占位脏数据。
        for field in ("保留天数", "归档路径", "清理方式"):
            entry[field] = str(values.get(field) or "").strip()
        entry["status"] = STATUS_ORDER[0]
        entry["策略状态"] = STATUS_ORDER[0]
        entry["最后操作"] = "登记策略"
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    # ------------------------------------------------------------------ 动作
    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        raw_action = str(action or "").strip()
        if not raw_action:
            return None, "未指定要执行的生命周期动作"
        if raw_action in REVOKE_ACTIONS:
            return None, "状态只允许按 草稿→生效中→已到期→已归档 前进，人工撤销不开放"
        canonical = ACTION_ALIASES.get(raw_action)
        if canonical is None:
            return (
                None,
                f"动作「{raw_action}」不属于表生命周期管理可执行范围"
                f"（可用：启用策略、删除表、归档表）",
            )

        with store.locked():
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"生命周期策略 {entry_id} 不存在或已归档"

            expected_from, target = TRANSITIONS[canonical]
            current = str(entry.get("status") or "")
            conclusion = ACTION_CONCLUSIONS[canonical]

            # 幂等重放：同一动作已经成功执行过，直接回读当前终态，不再写事件。
            if entry.get("最后操作") == conclusion and current == target:
                return entry, f"生命周期策略已{canonical}（动作已执行，请勿重复提交）"

            # 严格逐格推进：前置状态不匹配即拒绝（覆盖越级与回退）。
            if current != expected_from:
                allowed = self._next_action(current)
                hint = f"当前状态「{current}」只允许执行「{allowed}」" if allowed else "已归档为终态，不可再执行动作"
                return None, (
                    f"拒绝越级推进：动作「{canonical}」要求当前为「{expected_from}」，"
                    f"实际为「{current}」；{hint}"
                )

            before_status = current
            self._apply_transition(entry, canonical, target)
            self._write_audit(entry, canonical, before_status, target)
            self._sync_recycle(entry, canonical, before_status, target)
            return entry, f"生命周期策略已{canonical}"

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _next_action(current: str) -> str | None:
        for action, (from_status, _) in TRANSITIONS.items():
            if from_status == current:
                return action
        return None

    @staticmethod
    def _apply_transition(entry: dict[str, Any], canonical: str, target: str) -> None:
        entry["status"] = target
        entry["策略状态"] = target
        entry["最后操作"] = ACTION_CONCLUSIONS[canonical]
        entry["pending"] = target != FINAL_STATUS
        entry["abnormal"] = False

    @staticmethod
    def _write_audit(
        entry: dict[str, Any],
        canonical: str,
        before_status: str,
        target: str,
    ) -> None:
        """每次成功推进写且只写一条审计事件，编号在同一临界区内生成，天然唯一。"""
        audit_rows = store.rows(AUDIT_MODULE)
        next_id = max((int(row.get("id", 0)) for row in audit_rows), default=0) + 1
        policy_code = str(entry.get("策略编号", ""))
        # 序号按精确的来源策略编号统计，避免 LIFE-0001 与 LIFE-00010 之类前缀互相串号。
        seq = 1 + sum(
            1 for row in audit_rows if row.get("来源记录") == policy_code
        )
        code = f"AUDI-LIFE-{policy_code}-{seq:02d}"
        operated_at = _now_text()

        if canonical == "删除表":
            # 与回收站 RECY 记录的删除时间、可恢复期保持同一口径。
            deleted_at = operated_at
            recover_until = (
                datetime.strptime(operated_at, "%Y-%m-%d %H:%M:%S") + timedelta(days=7)
            ).strftime("%Y-%m-%d %H:%M:%S")
            before_value = f"策略状态={before_status}；删除时间={deleted_at}"
            after_value = f"策略状态={target}；可恢复期={recover_until}"
        else:
            before_value = f"策略状态={before_status}"
            after_value = f"策略状态={target}"

        audit_rows.append({
            "id": next_id,
            "status": "已记录",
            "pending": True,
            "abnormal": False,
            "记录编号": code,
            "变更对象": f"{entry.get('策略编号', '')} / {entry.get('表名称', '')}",
            "变更类型": canonical,
            "变更前值": before_value,
            "变更后值": after_value,
            "操作人": "值班管理员",
            "操作时间": operated_at,
            "复核状态": "已记录",
            # 回溯键：幂等与对账都靠它定位同一条生命周期动作。
            "来源模块": MODULE,
            "来源记录": entry.get("策略编号", ""),
            "来源动作": canonical,
        })

    @staticmethod
    def _sync_recycle(
        entry: dict[str, Any],
        canonical: str,
        before_status: str,
        target: str,
    ) -> None:
        """把生命周期结论同步到相邻业务入口回收站，状态必须与真实策略状态对应。"""
        recycle_rows = store.rows(RECYCLE_MODULE)
        table_name = str(entry.get("表名称", ""))
        policy_code = str(entry.get("策略编号", ""))
        existing = next(
            (row for row in recycle_rows if str(row.get("表名称", "")) == table_name),
            None,
        )

        if canonical == "删除表":
            deleted_at = _now_text()
            recover_until = (
                datetime.strptime(deleted_at, "%Y-%m-%d %H:%M:%S") + timedelta(days=7)
            ).strftime("%Y-%m-%d %H:%M:%S")
            if existing is None:
                existing = {
                    "id": max((int(row.get("id", 0)) for row in recycle_rows), default=0) + 1,
                    "记录编号": f"RECY-LIFE-{policy_code}",
                    "表名称": table_name,
                    "回收原因": f"生命周期策略 {policy_code} 到期清理",
                    "数据大小": "",
                    "清理时间": "",
                }
                recycle_rows.append(existing)
            existing["status"] = "待恢复"
            existing["pending"] = True
            existing["abnormal"] = False
            existing["删除时间"] = deleted_at
            existing["可恢复期"] = recover_until
            existing["恢复状态"] = "到期待回收"
        elif canonical == "归档表":
            if existing is not None:
                archived_at = _now_text()
                existing["status"] = "已过期"
                existing["pending"] = False
                existing["abnormal"] = False
                existing["恢复状态"] = "已归档"
                existing["清理时间"] = archived_at
