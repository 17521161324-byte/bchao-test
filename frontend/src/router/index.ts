/**
 * 路由配置 - 包含布局嵌套
 */
import { createRouter, createWebHistory } from 'vue-router'
import Layout from '@/components/Layout/index.vue'

const routes = [
  {
    path: '/',
    component: Layout,
    redirect: 'data',
    children: [
      { path: 'data', component: () => import('@/pages/DataImport/index.vue') },
      { path: 'model', component: () => import('@/pages/ModelConfig/index.vue') },
      { path: 'test', component: () => import('@/pages/SingleTest/index.vue') },
      { path: 'eval', component: () => import('@/pages/Evaluation/index.vue') },
      { path: 'history', component: () => import('@/pages/TestHistory/index.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
