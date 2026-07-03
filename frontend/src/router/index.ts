/**
 * 路由配置 - 包含布局嵌套
 */
import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/components/Layout/index.vue'

const routes = [
  {
    path: '/',
    component: Layout,
    redirect: '/data',
    children: [
      { path: 'data', component: () => import('@/pages/DataImport/index.vue') },
      { path: 'model', component: () => import('@/pages/ModelConfig/index.vue') },
      { path: 'experiments', component: () => import('@/pages/Experiments/index.vue') },
      { path: 'experiments/:id', component: () => import('@/pages/Experiments/ExperimentDetail.vue') },
      { path: 'experiments/:id/results', component: () => import('@/pages/Experiments/ExperimentResults.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
