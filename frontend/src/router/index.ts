import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
const Lifecycle = () => import('@/views/lifecycle/index.vue')
const Cost = () => import('@/views/cost/index.vue')
const Heatmap = () => import('@/views/heatmap/index.vue')
const Dag = () => import('@/views/dag/index.vue')
const Sla = () => import('@/views/sla/index.vue')
const Resource = () => import('@/views/resource/index.vue')
const Score = () => import('@/views/score/index.vue')
const Drift = () => import('@/views/drift/index.vue')
const Catalog = () => import('@/views/catalog/index.vue')
const Retention = () => import('@/views/retention/index.vue')
const Dedup = () => import('@/views/dedup/index.vue')
const Tier = () => import('@/views/tier/index.vue')
const Baseline = () => import('@/views/baseline/index.vue')
const Recycle = () => import('@/views/recycle/index.vue')
const Audit = () => import('@/views/audit/index.vue')
const Benchmark = () => import('@/views/benchmark/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/lifecycle', name: 'lifecycle', component: Lifecycle },
    { path: '/cost', name: 'cost', component: Cost },
    { path: '/heatmap', name: 'heatmap', component: Heatmap },
    { path: '/dag', name: 'dag', component: Dag },
    { path: '/sla', name: 'sla', component: Sla },
    { path: '/resource', name: 'resource', component: Resource },
    { path: '/score', name: 'score', component: Score },
    { path: '/drift', name: 'drift', component: Drift },
    { path: '/catalog', name: 'catalog', component: Catalog },
    { path: '/retention', name: 'retention', component: Retention },
    { path: '/dedup', name: 'dedup', component: Dedup },
    { path: '/tier', name: 'tier', component: Tier },
    { path: '/baseline', name: 'baseline', component: Baseline },
    { path: '/recycle', name: 'recycle', component: Recycle },
    { path: '/audit', name: 'audit', component: Audit },
    { path: '/benchmark', name: 'benchmark', component: Benchmark },
  ],
})

export default router
