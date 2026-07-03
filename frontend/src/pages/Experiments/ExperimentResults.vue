<template>
  <div class="page-container">
    <div class="page-header"><h2>实验结果</h2></div>

    <a-card title="指标汇总" style="margin-bottom: 16px">
      <a-row :gutter="16" v-if="metrics">
        <a-col :span="6">总任务: {{ metrics.total_tasks }}</a-col>
        <a-col :span="6">成功率: {{ (metrics.asr_success_rate * 100).toFixed(0) }}%</a-col>
        <a-col :span="6">LLM失败率: {{ (metrics.llm_failure_rate * 100).toFixed(0) }}%</a-col>
        <a-col :span="6">总成本: {{ metrics.total_cost }}</a-col>
      </a-row>
    </a-card>

    <a-table :data-source="results" row-key="id">
      <a-table-column title="任务ID" data-index="id" :width="80" />
      <a-table-column title="状态" data-index="status" :width="100">
        <template #default="{ record }">
          <a-tag :color="record.status === 'success' ? 'green' : record.status === 'failed' ? 'red' : 'default'">
            {{ record.status }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column title="阶段" data-index="stage" :width="80" />
      <a-table-column title="重试" data-index="retry_count" :width="60" />
      <a-table-column title="耗时" data-index="total_duration" :width="80" />
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { experimentApi } from '@/api/experiment'

const route = useRoute()
const batchId = computed(() => Number(route.params.id))
const metrics = ref<any>(null)
const results = ref<any[]>([])

onMounted(async () => {
  const [m, r] = await Promise.all([
    experimentApi.metrics(batchId.value),
    experimentApi.results(batchId.value),
  ])
  metrics.value = m.data
  results.value = r.data
})
</script>
