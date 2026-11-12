<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">数仓治理与运维平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向数据仓库团队的治理与运维一体化平台。覆盖表生命周期管理、存储成本优化、数据热度分析、任务依赖编排、SLA告警、资源弹性调度与数仓健康度评估的完整治理链路。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "表生命周期管理", path: "/lifecycle" }, { label: "存储成本优化", path: "/cost" }, { label: "数据热度分析", path: "/heatmap" }, { label: "任务依赖编排", path: "/dag" }, { label: "SLA告警管理", path: "/sla" }, { label: "资源弹性调度", path: "/resource" }, { label: "数仓健康度评估", path: "/score" }, { label: "数据漂移检测", path: "/drift" }, { label: "数据资产盘点", path: "/catalog" }, { label: "数据保留策略", path: "/retention" }, { label: "数据去重管理", path: "/dedup" }, { label: "数据分层规划", path: "/tier" }, { label: "基线监控管理", path: "/baseline" }, { label: "数据回收站", path: "/recycle" }, { label: "变更审计追踪", path: "/audit" }, { label: "查询性能分析", path: "/benchmark" }]
</script>
