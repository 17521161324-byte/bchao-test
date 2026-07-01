<template>
  <div class="page-container">
    <div class="page-header"><h2>结果评估</h2></div>

    <a-row :gutter="16">
      <a-col :span="14">
        <a-card title="测试记录">
          <template #extra>
            <a-button @click="fetchTests">刷新</a-button>
          </template>
          <a-table
            row-key="id"
            :loading="loading"
            :columns="columns"
            :data-source="tests"
            :pagination="{ pageSize: 10 }"
            size="small"
            :row-class-name="(r: TestRun) => r.id === selectedTest?.id ? 'ant-table-row-selected' : ''"
            @row-click="(record: TestRun) => handleSelectTest(record)"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'time'">
                {{ new Date(record.created_at).toLocaleString('zh-CN') }}
              </template>
              <template v-else-if="column.key === 'accuracy'">
                <a-tag v-if="record.accuracy !== null" :color="record.accuracy >= 0.8 ? 'green' : record.accuracy >= 0.5 ? 'orange' : 'red'">
                  {{ (record.accuracy * 100).toFixed(0) }}%
                </a-tag>
                <span v-else>-</span>
              </template>
              <template v-else-if="column.key === 'corrected'">
                <a-tag v-if="record.human_corrected" color="blue">已修正</a-tag>
                <a-tag v-else>未修正</a-tag>
              </template>
            </template>
          </a-table>
        </a-card>
      </a-col>

      <a-col :span="10">
        <a-card v-if="selectedTest" :title="`评估详情 - ${selectedTest.record_id}`">
          <template #extra>
            <a-button v-if="!editing" @click="startEdit"><EditOutlined />修正</a-button>
            <a-button v-else type="primary" @click="handleSaveCorrection"><SaveOutlined />保存</a-button>
          </template>

          <template v-if="selectedTest.evaluation">
            <a-row :gutter="8" style="margin-bottom: 16px">
              <a-col :span="8">
                <a-statistic title="总字段" :value="selectedTest.evaluation.total_fields" />
              </a-col>
              <a-col :span="8">
                <a-statistic title="正确" :value="selectedTest.evaluation.correct_fields" :value-style="{ color: '#52c41a' }" />
              </a-col>
              <a-col :span="8">
                <a-statistic title="准确率" :value="((selectedTest.evaluation.accuracy || 0) * 100).toFixed(1)" suffix="%" />
              </a-col>
            </a-row>

            <a-table
              :columns="evalColumns"
              :data-source="evalRows"
              :pagination="false"
              size="small"
              :row-class-name="(r: any) => r.match ? '' : 'diff-wrong'"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'match'">
                  <a-tag v-if="record.match" icon="check" color="success">正确</a-tag>
                  <a-tag v-else icon="close" color="error">错误</a-tag>
                </template>
              </template>
            </a-table>

            <a-form v-if="editing" style="margin-top: 16px">
              <a-form-item>
                <a-textarea v-model:value="editJson" :rows="10" style="font-family: monospace; font-size: 12px" />
              </a-form-item>
            </a-form>
          </template>

          <a-empty v-else description="无评估数据（可能缺少 ground truth）" />
        </a-card>

        <a-card v-else>
          <a-empty description="请选择一条测试记录" />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { EditOutlined, SaveOutlined } from '@ant-design/icons-vue'
import { testApi } from '@/api/client'
import type { TestRun } from '@/types'

const tests = ref<TestRun[]>([])
const loading = ref(false)
const selectedTest = ref<TestRun | null>(null)
const editing = ref(false)
const editJson = ref('')

async function fetchTests() {
  loading.value = true
  try {
    const data = await testApi.getHistory({ limit: 50 })
    tests.value = data as TestRun[]
  } finally {
    loading.value = false
  }
}

onMounted(fetchTests)

function handleSelectTest(test: TestRun) {
  selectedTest.value = test
  editing.value = false
  if (test.structured_result) {
    editJson.value = JSON.stringify(test.structured_result, null, 2)
  }
}

function startEdit() {
  editing.value = true
  if (selectedTest.value?.structured_result) {
    editJson.value = JSON.stringify(selectedTest.value.structured_result, null, 2)
  }
}

async function handleSaveCorrection() {
  if (!selectedTest.value) return
  try {
    const structured = JSON.parse(editJson.value)
    await testApi.updateEval(selectedTest.value.id, {
      structured_result: structured,
      human_corrected: true,
    })
    message.success('评估已保存')
    editing.value = false
    await fetchTests()
  } catch (e: any) {
    if (e?.message?.includes('JSON')) {
      message.error('JSON 格式有误')
    }
  }
}

const fieldLabels: Record<string, string> = {
  right_follicle_total: '右侧卵泡总数',
  left_follicle_total: '左侧卵泡总数',
  endometrium_thickness: '内膜厚度',
  endometrium_type: '内膜类型',
  right_ovary_length: '右卵巢长',
  right_ovary_width: '右卵巢宽',
  left_ovary_length: '左卵巢长',
  left_ovary_width: '左卵巢宽',
}

const evalRows = computed(() => {
  if (!selectedTest.value?.evaluation?.fields) return []
  return Object.entries(selectedTest.value.evaluation.fields).map(([key, val]: [string, any]) => ({
    field: fieldLabels[key] || key,
    identified: val.identified ?? '-',
    truth: val.truth ?? '-',
    diff: val.diff !== null && val.diff !== undefined ? String(val.diff) : '-',
    match: val.match,
    key,
  }))
})

const columns = [
  { title: '时间', key: 'time', width: 160 },
  { title: '病历号', dataIndex: 'record_id', key: 'record_id' },
  { title: 'ASR 模型', dataIndex: 'asr_model_id', key: 'asr', width: 100 },
  { title: '准确率', key: 'accuracy', width: 100 },
  { title: '人工修正', key: 'corrected', width: 80 },
]

const evalColumns = [
  { title: '字段', dataIndex: 'field', key: 'field' },
  { title: '识别值', dataIndex: 'identified', key: 'identified' },
  { title: '真实值', dataIndex: 'truth', key: 'truth' },
  { title: '差异', dataIndex: 'diff', key: 'diff' },
  { title: '结果', key: 'match' },
]
</script>
