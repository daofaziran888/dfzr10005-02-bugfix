"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import lifecycle as router_lifecycle
from app.routers import cost as router_cost
from app.routers import heatmap as router_heatmap
from app.routers import dag as router_dag
from app.routers import sla as router_sla
from app.routers import resource as router_resource
from app.routers import score as router_score
from app.routers import drift as router_drift
from app.routers import catalog as router_catalog
from app.routers import retention as router_retention
from app.routers import dedup as router_dedup
from app.routers import tier as router_tier
from app.routers import baseline as router_baseline
from app.routers import recycle as router_recycle
from app.routers import audit as router_audit
from app.routers import benchmark as router_benchmark

ROUTERS = [router_lifecycle, router_cost, router_heatmap, router_dag, router_sla, router_resource, router_score, router_drift, router_catalog, router_retention, router_dedup, router_tier, router_baseline, router_recycle, router_audit, router_benchmark]
