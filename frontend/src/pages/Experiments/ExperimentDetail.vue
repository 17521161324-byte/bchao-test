<template>
  <div class="page-container">
    <div class="page-header">
      <h2>{{ batch?.name || '实验详情' }}</h2>
      <a-space>
        <a-button @click="fetchData">刷新</a-button>
      </a-space>
    </div>

    <a-descriptions v-if="batch" bordered :column="2">
      <a-descriptions-item label="状态">
        <a-tag :color="statusColor(batch.status)">{{ batch.status }}</a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="总任务">{{ batch.total_tasks }}</a-descriptions-item>
      <a-descriptions-item label="成功">{{ batch.success_count }}</a-descriptions-item>
      <a-descriptions-item label="失败">{{ batch.failure_count }}</a-descriptions-item>
    </a-descriptions>

    <a-row :gutter="16" style="margin-top: 16px">
      <a-col>
        <a-button type="primary" @click="handleStart" :disabled="batch?.status === 'running'">启动</a-button>
      </a-col>
      <a-col>
        <a-button @click="handlePause" :disabled="batch?.status !== 'running'">暂停</a-button>
      </a-col>
      <a-col>
        <a-button @click="handleResume" :disabled="batch?.status !== 'paused'">继续</a-button>
      </a-col>
      <a-col>
        <a-button danger @click="handleCancel">取消</a-button>
      </a-col>
      <a-col>
        <router-link :to="`/experiments/${batchId}/results`"><a-button>查看结果</a-button></router-link>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { experimentApi } from '@/api/experiment'

const route = useRoute()
const batchId = computed(() => Number(route.params.id))
const batch = ref<any>(null)

async function fetchData() {
  const res = await experimentApi.get(batchId.value)
  batch.value = res.data
}

async function handleStart() {
  await experimentApi.start(batchId.value)
  message.success('已启动')
  fetchData()
}

async function handlePause() {
  await experimentApi.pause(batchId.value)
  message.success('已暂停')
  fetchData()
}

async function handleResume() {
  await experimentApi.resume(batchId.value)
  message.success('已继续')
  fetchData()
}

async function handleCancel() {
  await experimentApi.cancel(batchId.value)
  message.success('已取消')
  fetchData()
}

function statusColor(status: string): string {
  const colors: Record<string, string> = { pending: 'default', running: 'blue', paused: 'orange', partial: 'purple', completed: 'green', cancelled: 'red' }
  return colors[status] || 'default'
}

onMounted(fetchData)
</script>
