<template>
  <div class="page-container">
    <div class="page-header">
      <h2>批量实验</h2>
      <router-link to="/experiments/new"><a-button type="primary">新建实验</a-button></router-link>
    </div>

    <a-table :data-source="experiments" :loading="loading" row-key="id">
      <a-table-column title="名称" data-index="name" />
      <a-table-column title="状态">
        <template #default="{ record }">
          <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="总任务" data-index="total_tasks" :width="80" />
      <a-table-column title="成功" data-index="success_count" :width="80" />
      <a-table-column title="失败" data-index="failure_count" :width="80" />
      <a-table-column title="创建时间" data-index="created_at" :width="180" />
      <a-table-column title="操作" :width="100">
        <template #default="{ record }">
          <router-link :to="`/experiments/${record.id}`">查看</router-link>
        </template>
      </a-table-column>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { experimentApi } from '@/api/experiment'
import type { ExperimentBatch } from '@/types/experiment'

const experiments = ref<ExperimentBatch[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const res = await experimentApi.list()
    experiments.value = res.data
  } finally {
    loading.value = false
  }
})

function statusColor(status: string): string {
  const colors: Record<string, string> = {
    pending: 'default',
    running: 'blue',
    paused: 'orange',
    partial: 'purple',
    completed: 'green',
    cancelled: 'red',
  }
  return colors[status] || 'default'
}
</script>
