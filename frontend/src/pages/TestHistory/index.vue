<template>
  <div class="page-container">
    <div class="page-header">
      <h2>LLM 历史记录</h2>
      <a-space>
        <a-select
          placeholder="按病历号筛选"
          allow-clear
          show-search
          style="width: 160px"
          :value="filters.record_id"
          @change="(v: string) => { filters.record_id = v; fetchTests() }"
          :options="recordIdOptions"
        />
        <a-select
          placeholder="按LLM模型筛选"
          allow-clear
          style="width: 160px"
          :value="filters.llm_model_name"
          @change="(v: string) => { filters.llm_model_name = v; fetchTests() }"
          :options="llmModelOptions"
        />
        <a-select
          placeholder="按状态筛选"
          allow-clear
          style="width: 120px"
          :value="filters.status"
          @change="(v: string) => { filters.status = v; fetchTests() }"
          :options="[{value:'success',label:'成功'},{value:'failed',label:'失败'},{value:'running',label:'运行中'}]"
        />
        <a-button type="primary" @click="exportExcel"><RobotOutlined />导出 Excel</a-button>
        <a-button @click="fetchTests"><ReloadOutlined />刷新</a-button>
      </a-space>
    </div>

    <a-card title="LLM 处理历史">
      <template #extra>
        <span style="color: #999">共 {{ tests.length }} 条</span>
      </template>
      <a-table
        row-key="id"
        :loading="loading"
        :columns="columns"
        :data-source="tests"
        :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'record_id'">
            {{ record.record_id }}
            <div style="color: #999; font-size: 11px">exam#{{ record.exam_record_id }} | {{ record.date }}</div>
          </template>
          <template v-else-if="column.key === 'models'">
            <div>ASR: {{ record.asr_model_name || '-' }}</div>
            <div>LLM: {{ record.llm_model_name || '-' }}</div>
          </template>
          <template v-else-if="column.key === 'accuracy'">
            <a-tag v-if="record.accuracy != null" :color="record.accuracy >= 0.8 ? 'green' : record.accuracy >= 0.5 ? 'orange' : 'red'">
              {{ (record.accuracy * 100).toFixed(0) }}%
            </a-tag>
            <span v-else>-</span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.status === 'success' ? 'green' : record.status === 'failed' ? 'red' : 'blue'">
              {{ record.status }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'structured'">
            <span v-if="record.structured_result" style="color: #52c41a">有数据</span>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button size="small" @click="showDetail(record)"><EyeOutlined />详情</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      :title="`LLM 详情 - ${selectedTest?.record_id}`"
      :open="detailVisible"
      @cancel="detailVisible = false"
      :footer="null"
      width="800px"
    >
      <template v-if="selectedTest">
        <a-descriptions :column="2" size="small" bordered style="margin-bottom: 12px">
          <a-descriptions-item label="ID">{{ selectedTest.id }}</a-descriptions-item>
          <a-descriptions-item label="病历号">{{ selectedTest.record_id }}</a-descriptions-item>
          <a-descriptions-item label="检查记录ID">{{ selectedTest.exam_record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ selectedTest.date }}</a-descriptions-item>
          <a-descriptions-item label="ASR模型">{{ selectedTest.asr_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="LLM模型">{{ selectedTest.llm_model_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="提示词版本">{{ selectedTest.prompt_version }}</a-descriptions-item>
          <a-descriptions-item label="提示词长度">{{ selectedTest.prompt_len }}</a-descriptions-item>
          <a-descriptions-item label="准确率">
            {{ selectedTest.accuracy != null ? ((selectedTest.accuracy * 100).toFixed(1) + '%') : '-' }}
          </a-descriptions-item>
          <a-descriptions-item label="状态">{{ selectedTest.status }}</a-descriptions-item>
          <a-descriptions-item label="创建时间">{{ selectedTest.created_at }}</a-descriptions-item>
        </a-descriptions>

        <div v-if="selectedTest.summary_text" style="margin-bottom: 12px">
          <h4>LLM 总结:</h4>
          <div class="summary-box">{{ selectedTest.summary_text }}</div>
        </div>

        <div v-if="selectedTest.structured_result" style="margin-bottom: 12px">
          <h4>结构化结果:</h4>
          <pre class="code-box">{{ JSON.stringify(selectedTest.structured_result, null, 2) }}</pre>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, EyeOutlined, RobotOutlined } from '@ant-design/icons-vue'
import { testApi } from '@/api/client'

interface LlmHistoryRecord {
  id: number
  exam_record_id: number
  record_id: string
  date: string | null
  asr_model_name: string | null
  llm_model_name: string | null
  prompt_version: string
  prompt_len: number
  summary_text: string | null
  structured_result: any
  accuracy: number | null
  status: string
  error_message: string | null
  created_at: string | null
}

const tests = ref<LlmHistoryRecord[]>([])
const loading = ref(false)
const detailVisible = ref(false)
const selectedTest = ref<LlmHistoryRecord | null>(null)
const filters = ref<{
  record_id?: string
  llm_model_name?: string
  status?: string
}>({})

async function fetchTests() {
  loading.value = true
  try {
    const params: any = { limit: 200 }
    if (filters.value.record_id) params.record_id = filters.value.record_id
    if (filters.value.llm_model_name) params.llm_model_name = filters.value.llm_model_name
    if (filters.value.status) params.status = filters.value.status
    const data = await testApi.getLlmHistory(params)
    tests.value = data as LlmHistoryRecord[]
  } catch (e: any) {
    message.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function exportExcel() {
  const url = testApi.exportLlmHistory(filters.value)
  window.open(url, '_blank')
  message.success('正在导出...')
}

onMounted(fetchTests)

const recordIdOptions = computed(() => {
  const ids = Array.from(new Set(tests.value.map((t) => t.record_id)))
  return ids.map((id) => ({ value: id, label: id }))
})

const llmModelOptions = computed(() => {
  const names = Array.from(new Set(tests.value.map((t) => t.llm_model_name).filter(Boolean)))
  return names.map((n) => ({ value: n, label: n }))
})

function showDetail(test: LlmHistoryRecord) {
  selectedTest.value = test
  detailVisible.value = true
}

const columns = [
  { title: '病历号', key: 'record_id', width: 120 },
  { title: '模型 (ASR/LLM)', key: 'models', width: 180 },
  { title: '状态', key: 'status', width: 90 },
  { title: '准确率', key: 'accuracy', width: 90 },
  { title: '结构化数据', key: 'structured', width: 90 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160 },
  { title: '操作', key: 'actions', width: 90 },
]
</script>

<style scoped>
.summary-box { padding: 12px; background: #f6ffed; border-radius: 4px; white-space: pre-wrap; font-size: 13px; }
.code-box { padding: 12px; background: #f5f5f5; border-radius: 4px; font-size: 12px; max-height: 400px; overflow: auto; }
</style>
