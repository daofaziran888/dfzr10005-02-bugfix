<template>
  <section class="page" data-module="lifecycle">
    <header class="page-head">
      <div>
        <h2>表生命周期管理管理</h2>
        <p class="page-desc">维护数仓表的生命周期策略定义、归档路径与清理方式，为表生命周期管理提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记生命周期策略</button>
        <button class="btn" type="button" @click="exportRows">导出表生命周期管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-if="row['可执行动作']"
              class="link"
              type="button"
              :disabled="busyId === String(row.id)"
              @click="runAction(String(row['可执行动作']), row)"
            >
              {{ busyId === String(row.id) ? '处理中…' : row['可执行动作'] }}
            </button>
            <span v-else class="muted-text">已归档（终态）</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无表生命周期管理数据，可先登记生命周期策略</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条表生命周期管理记录</span>
      <span v-if="feedback" :class="feedbackOk ? 'success-text' : 'error-text'">{{ feedback }}</span>
    </footer>

    <div v-if="createOpen" class="modal-overlay" @click.self="closeCreate">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记生命周期策略</h3>
        <label v-for="field in createFields" :key="field.name" class="modal-field">
          <span>{{ field.label }}<em v-if="field.required">*</em></span>
          <input v-model="createForm[field.name]" :placeholder="field.placeholder" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/lifecycle'
const columns = ["策略编号", "表名称", "创建日期", "保留天数", "归档路径", "清理方式", "最后操作", "策略状态"]
const stats = ref([
  { label: "生命周期策略总数", value: 0 },
  { label: "生效中策略", value: 0 },
  { label: "已到期策略", value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const feedback = ref('')
const feedbackOk = ref(false)
const busyId = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const createFields = [
  { name: '策略编号', label: '策略编号', required: true, placeholder: '如 LIFE-0004' },
  { name: '表名称', label: '表名称', required: true, placeholder: '如 ods_order_detail' },
  { name: '创建日期', label: '创建日期', required: true, placeholder: '如 2026-11-13' },
  { name: '保留天数', label: '保留天数', required: false, placeholder: '如 90' },
  { name: '归档路径', label: '归档路径', required: false, placeholder: '如 oss://dw-archive/表名/' },
  { name: '清理方式', label: '清理方式', required: false, placeholder: '如 先归档后删除' },
] as const

const createOpen = ref(false)
const submitting = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createError.value = ''
  createOpen.value = true
}

function closeCreate() {
  if (submitting.value) return
  createOpen.value = false
  createError.value = ''
}

async function submitCreate() {
  createError.value = ''
  submitting.value = true
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      createError.value = payload.message || '生命周期策略登记失败'
      return
    }
    createOpen.value = false
    feedback.value = '生命周期策略已登记，初始状态为草稿'
    feedbackOk.value = true
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '生命周期策略登记失败'
  } finally {
    submitting.value = false
  }
}

async function runAction(action: string, row: Row) {
  feedback.value = ''
  busyId.value = String(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 越级/回退/重放/并发争抢的业务裁决结果，原样展示，不残留旧提示。
      feedback.value = payload.message || '表生命周期管理动作未生效，请稍后重试'
      feedbackOk.value = false
    } else {
      feedback.value = payload.message || '动作已执行'
      feedbackOk.value = true
    }
    await reload()
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '表生命周期管理操作失败'
    feedbackOk.value = false
  } finally {
    busyId.value = ''
  }
}

async function reload() {
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, statResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}?page=1&size=10000`),
    ])
    if (!listResponse.ok) {
      throw new Error('生命周期策略列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length

    if (statResponse.ok) {
      const statPayload = await statResponse.json()
      const all: Row[] = statPayload.items ?? []
      stats.value = [
        { label: "生命周期策略总数", value: statPayload.total ?? all.length },
        { label: "生效中策略", value: all.filter((item) => item.status === '生效中').length },
        { label: "已到期策略", value: all.filter((item) => item.status === '已到期').length },
      ]
    }
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '表生命周期管理列表读取失败'
    feedbackOk.value = false
  }
}

onMounted(reload)
</script>
