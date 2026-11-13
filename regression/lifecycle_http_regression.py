"""生命周期 HTTP 端到端回归：直接打真实 uvicorn 接口（仅标准库）。

前置：后端已在 127.0.0.1:8011 运行。脚本启动时通过重启口径保证种子态——
这里通过对同一进程的只读/动作接口验证，不依赖额外管理端点。
"""
from __future__ import annotations

import concurrent.futures
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8011"
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


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def find_policy(code: str) -> dict:
    _, payload = call("GET", "/api/lifecycle?size=200")
    return next(item for item in payload["items"] if item["策略编号"] == code)


def find_id(code: str) -> int:
    return int(find_policy(code)["id"])


def audit_codes(policy: str) -> list[str]:
    _, payload = call("GET", "/api/audit?size=200")
    return [r["记录编号"] for r in payload["items"] if r.get("来源记录") == policy]


def main() -> int:
    print("【H1】列表返回每行唯一可执行动作，且与状态匹配")
    _, payload = call("GET", "/api/lifecycle?size=200")
    by_status = {item["status"]: item for item in payload["items"]}
    check("草稿行只允许启用策略", by_status["草稿"]["可执行动作"] == "启用策略")
    check("生效中行只允许删除表", by_status["生效中"]["可执行动作"] == "删除表")
    check("已到期行只允许归档表", by_status["已到期"]["可执行动作"] == "归档表")

    print("【H2】原故障复现路径：LIFE-0001 草稿点删除表必须被拒绝")
    life1 = find_id("LIFE-0001")
    status, result = call("POST", f"/api/lifecycle/{life1}/actions", {"values": {"action": "删除表"}})
    check("HTTP 200 且业务 ok=False", status == 200 and result["ok"] is False, str(result))
    check("状态仍是草稿", find_policy("LIFE-0001")["status"] == "草稿")
    check("不产生审计事件", audit_codes("LIFE-0001") == [])

    print("【H3】旧的错误请求体 {action} 不再被静默吞掉（缺动作给出明确报错）")
    status, result = call("POST", f"/api/lifecycle/{life1}/actions", {"action": "启用策略"})
    check("缺动作明确报错而非空转", result["ok"] is False and "未指定" in result["message"], str(result))

    print("【H4】正常顺序推进，每步一条唯一审计")
    for action, target in [("启用策略", "生效中"), ("删除表", "已到期"), ("归档表", "已归档")]:
        status, result = call("POST", f"/api/lifecycle/{life1}/actions", {"values": {"action": action}})
        check(f"{action} 成功到 {target}", result["ok"] and result["entry"]["status"] == target, str(result))
    check("三条审计且编号唯一", len(set(audit_codes("LIFE-0001"))) == 3)

    print("【H5】同动作重放幂等，不写第二条事件")
    before = len(audit_codes("LIFE-0001"))
    status, result = call("POST", f"/api/lifecycle/{life1}/actions", {"values": {"action": "归档表"}})
    check("重放返回成功提示", result["ok"] and "请勿重复提交" in result["message"])
    check("审计不增加", len(audit_codes("LIFE-0001")) == before)

    print("【H6】已归档回退到草稿的老故障必须拒绝")
    status, result = call("POST", f"/api/lifecycle/{life1}/actions", {"values": {"action": "启用策略"}})
    check("回退拒绝", result["ok"] is False and "越级" in result["message"], str(result))
    check("终态保持已归档", find_policy("LIFE-0001")["status"] == "已归档")

    print("【H7】并发请求争抢同一条策略，只有一个推进结果")
    life3 = find_id("LIFE-0003")  # 种子为已到期，合法动作为归档表
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(call, "POST", f"/api/lifecycle/{life3}/actions", {"values": {"action": "归档表"}})
            for _ in range(8)
        ]
        responses = [f.result() for f in futures]
    msgs = [r[1]["message"] for r in responses]
    fresh = [m for m in msgs if "请勿重复提交" not in m]
    replay = [m for m in msgs if "请勿重复提交" in m]
    check("恰好一个请求真正完成推进（新鲜成功仅一条）", len(fresh) == 1, str(msgs))
    check("其余请求走幂等分支读取相同终态", len(replay) == 7, str(msgs))
    check("所有请求都读到已归档终态", all(r[1]["entry"] and r[1]["entry"]["status"] == "已归档" for r in responses))
    check("所有请求读到的终态一致为已归档", find_policy("LIFE-0003")["status"] == "已归档")
    check("只写一条归档审计", len(audit_codes("LIFE-0003")) == 1)

    print("【H8】回收站与审计清单可查询且状态对账")
    _, recycle = call("GET", "/api/recycle?size=200")
    recy1 = next(r for r in recycle["items"] if r["记录编号"] == "RECY-0001")
    check("RECY-0001 随归档显示已归档", recy1["恢复状态"] == "已归档" and recy1["status"] == "已过期", str(recy1))
    _, audits = call("GET", "/api/audit?size=200")
    delete_ev = next(
        r for r in audits["items"]
        if r.get("来源记录") == "LIFE-0001" and r["变更类型"] == "删除表"
    )
    check("审计前值含 RECY-0001 删除时间", recy1["删除时间"] in delete_ev["变更前值"])
    check("审计后值含 RECY-0001 可恢复期", recy1["可恢复期"] in delete_ev["变更后值"])

    print("【H9】概览待处理量与列表一致")
    _, overview = call("GET", "/api/overview")
    lc = next(m for m in overview["modules"] if m["name"] == "lifecycle")
    _, listed = call("GET", "/api/lifecycle?size=200")
    pending_count = sum(1 for r in listed["items"] if r["pending"])
    check("概览待处理=列表 pending", lc["pending"] == pending_count, f"{lc['pending']} vs {pending_count}")

    print(f"\nHTTP 回归结果：通过 {PASS} 项，失败 {FAIL} 项")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
