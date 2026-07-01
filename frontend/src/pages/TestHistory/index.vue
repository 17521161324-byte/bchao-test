<template>
  <div class="page-container">
    <div class="page-header"><h2>测试历史</h2></div>

    <a-card title="历史记录">
      <template #extra>
        <a-space>
          <a-select
            placeholder="按病历号筛选"
            allow-clear
            show-search
            style="width: 160px"
            @change="(v: string) => filters.record_id = v"
            :options="Array.from(new Set(tests.map((t) => t.record_id))).map((id) => ({ value: id, label: id }))"
          />
          <a-button @click="fetchTests"><ReloadOutlined />刷新</a-button>
        </a-space>
      </template>

      <a-table
        row-key="id"
        :loading="loading"
        :columns="columns"
        :data-source="filteredTests"
        :pagination="{ pageSize: 20, showSizeChanger: true }"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'time'">
            {{ new Date(record.created_at).toLocaleString('zh-CN') }}
          </template>
          <template v-else-if="column.key === 'llm'">
            {{ record.llm_model_id ?? '-' }}
          </template>
          <template v-else-if="column.key === 'accuracy'">
            <a-tag v-if="record.accuracy !== null" :color="record.accuracy >= 0.8 ? 'green' : record.accuracy >= 0.5 ? 'orange' : 'red'">
              {{ (record.accuracy * 100).toFixed(0) }}%
            </a-tag>
            <span v-else>-</span>
          </template>
          <template v-else-if="column.key === 'duration'">
            {{ record.duration_seconds.toFixed(1) }}s
          </template>
          <template v-else-if="column.key === 'corrected'">
            <a-tag v-if="record.human_corrected" color="blue">是</a-tag>
            <a-tag v-else>否</a-tag>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button size="small" @click="showDetail(record)"><EyeOutlined />详情</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      :title="`测试详情 - ${selectedTest?.record_id}`"
      :open="detailVisible"
      @cancel="detailVisible = false"
      :footer="null"
      :width="700"
    >
      <template v-if="selectedTest">
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="测试时间">{{ new Date(selectedTest.created_at).toLocaleString('zh-CN') }}</a-descriptions-item>
          <a-descriptions-item label="病历号">{{ selectedTest.record_id }}</a-descriptions-item>
          <a-descriptions-item label="ASR 模型 ID">{{ selectedTest.asr_model_id }}</a-descriptions-item>
          <a-descriptions-item label="LLM 模型 ID">{{ selectedTest.llm_model_id ?? '-' }}</a-descriptions-item>
          <a-descriptions-item label="准确率">
            {{ selectedTest.accuracy !== null ? `${(selectedTest.accuracy * 100).toFixed(1)}%` : '-' }}
          </a-descriptions-item>
          <a-descriptions-item label="耗时">{{ selectedTest.duration_seconds }}s</a-descriptions-item>
        </a-descriptions>

        <div v-if="selectedTest.full_transcript" style="margin-top: 16px">
          <h4>完整转写：</h4>
          <div class="transcript-box">{{ selectedTest.full_transcript }}</div>
        </div>

        <div v-if="selectedTest.summary_text" style="margin-top: 16px">
          <h4>总结：</h4>
          <div class="summary-box">{{ selectedTest.summary_text }}</div>
        </div>

        <div v-if="selectedTest.structured_result" style="margin-top: 16px">
          <h4>结构化结果：</h4>
          <pre class="code-box">{{ JSON.stringify(selectedTest.structured_result, null, 2) }}</pre>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ReloadOutlined, EyeOutlined } from '@ant-design/icons-vue'
import { testApi } from '@/api/client'
import type { TestRun } from '@/types'

const tests = ref<TestRun[]>([])
const loading = ref(false)
const detailVisible = ref(false)
const selectedTest = ref<TestRun | null>(null)
const filters = ref<{ record_id?: string }>({})

async function fetchTests() {
  loading.value = true
  try {
    const params: any = { limit: 100 }
    if (filters.value.record_id) params.record_id = filters.value.record_id
    const data = await testApi.getHistory(params)
    tests.value = data as TestRun[]
  } finally {
    loading.value = false
  }
}

onMounted(fetchTests)

const filteredTests = computed(() => {
  if (!filters.value.record_id) return tests.value
  return tests.value.filter((t) => t.record_id === filters.value.record_id)
})

function showDetail(test: TestRun) {
  selectedTest.value = test
  detailVisible.value = true
}

const columns = [
  { title: '测试时间', key: 'time', width: 180,
    sorter: (a: TestRun, b: TestRun) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    defaultSortOrder: 'descend' as const,
  },
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', width: 120 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 100 },
  { title: 'ASR 模型 ID', dataIndex: 'asr_model_id', key: 'asr', width: 100 },
  { title: 'LLM 模型 ID', key: 'llm', width: 100 },
  { title: '准确率', key: 'accuracy', width: 100 },
  { title: '耗时', key: 'duration', width: 80 },
  { title: '人工修正', key: 'corrected', width: 80 },
  { title: '操作', key: 'actions', width: 100 },
]
</script>

<style scoped>
.transcript-box { padding: 12px; background: #f5f5f5; border-radius: 4px; max-height: 200px; overflow: auto; font-size: 13px; }
.summary-box { padding: 12px; background: #f6ffed; border-radius: 4px; }
.code-box { padding: 12px; background: #f5f5f5; border-radius: 4px; font-size: 12px; }
</style>
