<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "表生命周期管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "存储成本优化", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据热度分析", "created": 0, "pending": 0, "abnormal": 0}, {"name": "任务依赖编排", "created": 0, "pending": 0, "abnormal": 0}, {"name": "SLA告警管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "资源弹性调度", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数仓健康度评估", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据漂移检测", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据资产盘点", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据保留策略", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据去重管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据分层规划", "created": 0, "pending": 0, "abnormal": 0}, {"name": "基线监控管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据回收站", "created": 0, "pending": 0, "abnormal": 0}, {"name": "变更审计追踪", "created": 0, "pending": 0, "abnormal": 0}, {"name": "查询性能分析", "created": 0, "pending": 0, "abnormal": 0}]
  }
})
</script>
