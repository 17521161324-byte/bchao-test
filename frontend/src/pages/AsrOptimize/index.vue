<template>
  <div class="asr-optimize-page">
    <a-card class="page-card">
      <template #title>
        <a-space direction="vertical" :size="2">
          <span>ASR 优化评估</span>
          <span class="sub-title">对比分段、整段、平台热词、上下文热词等 ASR 方案的文本变化，再决定是否进入后续 LLM 评估</span>
        </a-space>
      </template>
      <template #extra>
        <a-space wrap>
          <a-button @click="loadAll" :loading="loading">刷新</a-button>
          <a-button :disabled="!canExport" @click="exportCsv">导出评估 CSV</a-button>
          <a-button type="primary" :disabled="!canRunMissing" :loading="batchRunning" @click="runBatch('missing')">补齐未转写</a-button>
          <a-button danger :disabled="!canForceRun" :loading="batchRunning" @click="runBatch('force')">重跑选中变体</a-button>
        </a-space>
      </template>

      <a-alert
        class="tip"
        type="info"
        show-icon
        message="建议先选一个基线 ASR，再选择多个参数变体。系统会对每条检查记录计算 ASR 文本是否变化、变化率、数字漏识别/多识别。"
      />

      <div class="filters">
        <a-space wrap>
          <span class="label">批次</span>
          <a-select v-model:value="selectedDate" style="width: 190px" :options="dateOptions" @change="loadAsrResults" />

          <span class="label">ASR 变体</span>
          <a-select
            v-model:value="selectedModelIds"
            mode="multiple"
            style="min-width: 420px"
            :max-tag-count="3"
            :options="modelOptions"
            placeholder="选择要评估的 ASR 配置"
          />

          <span class="label">基线</span>
          <a-select
            v-model:value="baselineModelId"
            style="width: 220px"
            :options="baselineOptions"
            placeholder="选择基线 ASR"
          />

          <a-input-search v-model:value="keyword" allow-clear style="width: 220px" placeholder="搜索病历号" />
        </a-space>
      </div>

      <a-card v-if="batchRunning || batchStats.total > 0" size="small" class="progress-card">
        <a-space direction="vertical" style="width: 100%">
          <a-space wrap>
            <a-tag color="blue">总任务 {{ batchStats.total }}</a-tag>
            <a-tag color="green">成功 {{ batchStats.success }}</a-tag>
            <a-tag color="default">跳过 {{ batchStats.skipped }}</a-tag>
            <a-tag color="red">失败 {{ batchStats.failed }}</a-tag>
            <span class="muted">{{ batchStats.current || '等待执行' }}</span>
          </a-space>
          <a-progress :percent="batchPercent" size="small" />
        </a-space>
      </a-card>

      <div class="summary-grid">
        <a-card v-for="item in modelSummaries" :key="item.modelId" size="small" class="summary-card">
          <div class="summary-title">{{ item.modelName }}</div>
          <div class="summary-line">
            <a-tag :color="item.modelId === baselineModelId ? 'blue' : 'default'">
              {{ item.modelId === baselineModelId ? '基线' : '变体' }}
            </a-tag>
            <a-tag color="green">成功 {{ item.success }}</a-tag>
            <a-tag color="orange">变化 {{ item.changed }}</a-tag>
            <a-tag color="red">失败 {{ item.failed }}</a-tag>
          </div>
          <div class="summary-metric">
            平均变化率：{{ formatPercent(item.averageChangeRate) }}
          </div>
          <div class="summary-metric">
            数字差异：漏 {{ item.missingNumbers }} / 多 {{ item.extraNumbers }}
          </div>
          <div class="summary-config">{{ item.configSummary }}</div>
        </a-card>
      </div>

      <a-tabs>
        <a-tab-pane key="detail" tab="评估明细">
          <a-table
            :columns="detailColumns"
            :data-source="filteredEvaluationRows"
            :loading="loading"
            :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }"
            :row-selection="{ selectedRowKeys, onChange: onSelectRows }"
            :scroll="{ x: 'max-content' }"
            row-key="key"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.dataIndex === 'status'">
                <a-tag :color="statusColor(record.status)">{{ statusText(record.status) }}</a-tag>
              </template>
              <template v-else-if="column.dataIndex === 'is_baseline'">
                <a-tag :color="record.is_baseline ? 'blue' : 'default'">{{ record.is_baseline ? '基线' : '变体' }}</a-tag>
              </template>
              <template v-else-if="column.dataIndex === 'changed'">
                <a-tag :color="record.is_baseline ? 'blue' : record.changed ? 'orange' : 'green'">
                  {{ record.is_baseline ? '基线' : record.changed ? '有变化' : '无变化' }}
                </a-tag>
              </template>
              <template v-else-if="column.dataIndex === 'change_rate'">
                {{ record.is_baseline ? '-' : formatPercent(record.change_rate) }}
              </template>
              <template v-else-if="column.dataIndex === 'number_diff'">
                <div v-if="record.is_baseline" class="muted">-</div>
                <div v-else class="number-diff">
                  <div v-if="record.missing_numbers.length">漏识别：{{ compactNumbers(record.missing_numbers) }}</div>
                  <div v-if="record.extra_numbers.length">多识别：{{ compactNumbers(record.extra_numbers) }}</div>
                  <span v-if="!record.missing_numbers.length && !record.extra_numbers.length" class="muted">无数字差异</span>
                </div>
              </template>
              <template v-else-if="column.dataIndex === 'transcript'">
                <div class="transcript-preview" @click="openDetail(record)">{{ record.transcript || record.error_message || '暂无文本' }}</div>
              </template>
              <template v-else-if="column.dataIndex === 'config'">
                <a-tooltip :title="record.config_detail">
                  <span class="config-text">{{ record.config_summary }}</span>
                </a-tooltip>
              </template>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="matrix" tab="文本变化矩阵">
          <a-table
            :columns="matrixColumns"
            :data-source="matrixRows"
            :pagination="{ pageSize: 20, showSizeChanger: true }"
            :scroll="{ x: 'max-content' }"
            row-key="id"
            size="small"
          />
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <a-modal v-model:open="detailOpen" width="1100px" :title="detailTitle" :footer="null">
      <template v-if="detailRow">
        <a-descriptions size="small" bordered :column="2">
          <a-descriptions-item label="病历号">{{ detailRow.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ detailRow.date }}</a-descriptions-item>
          <a-descriptions-item label="ASR方案">{{ detailRow.model_name }}</a-descriptions-item>
          <a-descriptions-item label="配置">{{ detailRow.config_summary }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="statusColor(detailRow.status)">{{ statusText(detailRow.status) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="变化率">{{ detailRow.is_baseline ? '-' : formatPercent(detailRow.change_rate) }}</a-descriptions-item>
        </a-descriptions>

        <a-divider orientation="left">当前 ASR 转写</a-divider>
        <div class="transcript-box">{{ detailRow.transcript || detailRow.error_message || '暂无文本' }}</div>

        <template v-if="!detailRow.is_baseline">
          <a-divider orientation="left">基线 ASR 转写</a-divider>
          <div class="transcript-box baseline">{{ detailRow.baseline_transcript || '暂无基线文本' }}</div>

          <a-divider orientation="left">数字差异</a-divider>
          <a-space direction="vertical" style="width: 100%">
            <a-alert v-if="detailRow.missing_numbers.length" type="warning" :message="`漏识别：${compactNumbers(detailRow.missing_numbers)}`" />
            <a-alert v-if="detailRow.extra_numbers.length" type="error" :message="`多识别：${compactNumbers(detailRow.extra_numbers)}`" />
            <a-empty v-if="!detailRow.missing_numbers.length && !detailRow.extra_numbers.length" description="未发现数字集合差异" />
          </a-space>
        </template>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { audioApi, modelApi, patientApi } from '@/api/client'
import type { ModelConfig, PatientExamination } from '@/types'

type AsrResult = {
  id: number
  patient_id: number
  record_id: string
  date: string
  asr_model_id: number
  model_name?: string
  full_model_name?: string
  provider?: string
  segments?: any[]
  full_transcript?: string
  status?: string
  error_message?: string
  created_at?: string
}

type EvalRow = {
  key: string
  record_id: string
  patient_id: number
  date: string
  model_id: number
  model_name: string
  is_baseline: boolean
  status: string
  changed: boolean
  change_rate: number
  missing_numbers: string[]
  extra_numbers: string[]
  transcript: string
  baseline_transcript: string
  error_message: string
  config_summary: string
  config_detail: string
}

const loading = ref(false)
const batchRunning = ref(false)
const records = ref<PatientExamination[]>([])
const asrModels = ref<ModelConfig[]>([])
const selectedDate = ref<string>('all')
const selectedModelIds = ref<number[]>([])
const baselineModelId = ref<number | undefined>(undefined)
const keyword = ref('')
const asrResultsByRecord = ref<Record<string, Record<string, AsrResult>>>({})
const selectedRowKeys = ref<(string | number)[]>([])
const detailOpen = ref(false)
const detailRow = ref<EvalRow | null>(null)

const batchStats = ref({
  total: 0,
  done: 0,
  success: 0,
  skipped: 0,
  failed: 0,
  current: '',
})

const detailColumns = [
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', fixed: 'left', width: 105 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 105 },
  { title: '角色', dataIndex: 'is_baseline', key: 'is_baseline', width: 85 },
  { title: 'ASR方案', dataIndex: 'model_name', key: 'model_name', width: 180 },
  { title: '配置摘要', dataIndex: 'config', key: 'config', width: 230 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '是否变化', dataIndex: 'changed', key: 'changed', width: 100 },
  { title: '变化率', dataIndex: 'change_rate', key: 'change_rate', width: 90, sorter: (a: EvalRow, b: EvalRow) => a.change_rate - b.change_rate },
  { title: '医学数字差异', dataIndex: 'number_diff', key: 'number_diff', width: 220 },
  { title: 'ASR转写文本', dataIndex: 'transcript', key: 'transcript', width: 520 },
]

const dateOptions = computed(() => {
  const counts = new Map<string, number>()
  records.value.forEach((item) => counts.set(item.date, (counts.get(item.date) || 0) + 1))
  const dates = Array.from(counts.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, count]) => ({ label: `${date}（${count}）`, value: date }))
  return [{ label: `全部（${records.value.length}）`, value: 'all' }, ...dates]
})

const modelOptions = computed(() =>
  asrModels.value.map((model) => ({
    label: `${model.name}${model.status === 'active' ? '' : '（未启用）'} · ${modelConfigSummary(model)}`,
    value: model.id,
    disabled: model.status !== 'active',
  })),
)

const baselineOptions = computed(() =>
  selectedModelIds.value.map((id) => ({
    label: getModelName(id),
    value: id,
  })),
)

const filteredRecords = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return records.value.filter((record) => {
    const dateMatched = selectedDate.value === 'all' || record.date === selectedDate.value
    const keywordMatched = !kw || String(record.record_id || '').toLowerCase().includes(kw)
    return dateMatched && keywordMatched
  })
})

const evaluationRows = computed<EvalRow[]>(() => {
  if (!selectedModelIds.value.length) return []
  const baselineId = baselineModelId.value || selectedModelIds.value[0]
  const rows: EvalRow[] = []

  filteredRecords.value.forEach((record) => {
    const baselineResult = getCellResult(record, baselineId)
    const baselineText = normalizeTranscript(baselineResult?.full_transcript || '')
    selectedModelIds.value.forEach((modelId) => {
      const model = getModel(modelId)
      const result = getCellResult(record, modelId)
      const transcript = normalizeTranscript(result?.full_transcript || '')
      const isBaseline = modelId === baselineId
      const diff = isBaseline ? { rate: 0, changed: false } : textDiff(baselineText, transcript)
      const numberDiff = isBaseline ? { missing: [], extra: [] } : diffNumbers(extractMedicalNumbers(baselineText), extractMedicalNumbers(transcript))
      rows.push({
        key: `${record.id}:${modelId}`,
        record_id: record.record_id,
        patient_id: record.id,
        date: record.date,
        model_id: modelId,
        model_name: getModelName(modelId),
        is_baseline: isBaseline,
        status: result?.status || 'missing',
        changed: diff.changed || numberDiff.missing.length > 0 || numberDiff.extra.length > 0,
        change_rate: diff.rate,
        missing_numbers: numberDiff.missing,
        extra_numbers: numberDiff.extra,
        transcript,
        baseline_transcript: baselineText,
        error_message: result?.error_message || '',
        config_summary: model ? modelConfigSummary(model) : '-',
        config_detail: model ? JSON.stringify(model.params || {}, null, 2) : '-',
      })
    })
  })

  return rows
})

const filteredEvaluationRows = computed(() => evaluationRows.value)

const matrixColumns = computed(() => {
  const base = [
    { title: '病历号', dataIndex: 'record_id', key: 'record_id', fixed: 'left', width: 105 },
    { title: '日期', dataIndex: 'date', key: 'date', width: 105 },
  ]
  const dynamic = selectedModelIds.value.map((modelId) => ({
    title: getModelName(modelId),
    dataIndex: `model_${modelId}`,
    key: `model_${modelId}`,
    width: 210,
  }))
  return [...base, ...dynamic]
})

const matrixRows = computed(() => {
  const rowsByRecord = new Map<number, any>()
  evaluationRows.value.forEach((row) => {
    if (!rowsByRecord.has(row.patient_id)) {
      rowsByRecord.set(row.patient_id, {
        id: row.patient_id,
        record_id: row.record_id,
        date: row.date,
      })
    }
    const target = rowsByRecord.get(row.patient_id)
    target[`model_${row.model_id}`] = row.is_baseline
      ? '基线'
      : `${row.changed ? '有变化' : '无变化'} / ${formatPercent(row.change_rate)} / 漏${row.missing_numbers.length} 多${row.extra_numbers.length}`
  })
  return Array.from(rowsByRecord.values())
})

const modelSummaries = computed(() => selectedModelIds.value.map((modelId) => {
  const rows = evaluationRows.value.filter((row) => row.model_id === modelId)
  const successful = rows.filter((row) => row.status === 'success')
  const changedRows = rows.filter((row) => !row.is_baseline && row.changed)
  const averageChangeRate = changedRows.length
    ? changedRows.reduce((sum, row) => sum + row.change_rate, 0) / changedRows.length
    : 0
  return {
    modelId,
    modelName: getModelName(modelId),
    total: rows.length,
    success: successful.length,
    failed: rows.filter((row) => row.status === 'failed').length,
    missing: rows.filter((row) => row.status === 'missing').length,
    changed: changedRows.length,
    averageChangeRate,
    missingNumbers: rows.reduce((sum, row) => sum + row.missing_numbers.length, 0),
    extraNumbers: rows.reduce((sum, row) => sum + row.extra_numbers.length, 0),
    configSummary: modelConfigSummary(getModel(modelId)),
  }
}))

const batchPercent = computed(() => {
  if (!batchStats.value.total) return 0
  return Math.round((batchStats.value.done / batchStats.value.total) * 100)
})

const selectedEvalRows = computed(() => {
  const selected = new Set(selectedRowKeys.value.map(String))
  return evaluationRows.value.filter((row) => selected.has(row.key))
})

const canRunMissing = computed(() =>
  selectedModelIds.value.length > 0 && evaluationRows.value.some((row) => row.status === 'missing') && !batchRunning.value,
)

const canForceRun = computed(() =>
  selectedEvalRows.value.length > 0 && !batchRunning.value,
)

const canExport = computed(() => evaluationRows.value.length > 0)

const detailTitle = computed(() => {
  if (!detailRow.value) return 'ASR 评估详情'
  return `${detailRow.value.record_id} / ${detailRow.value.date} / ${detailRow.value.model_name}`
})

watch(selectedModelIds, (ids) => {
  if (!ids.length) {
    baselineModelId.value = undefined
    return
  }
  if (!baselineModelId.value || !ids.includes(baselineModelId.value)) {
    baselineModelId.value = ids[0]
  }
})

onMounted(loadAll)

async function loadAll() {
  loading.value = true
  try {
    const [recordData, modelData] = await Promise.all([
      audioApi.getRecords(),
      modelApi.list('asr'),
    ])
    records.value = recordData as PatientExamination[]
    asrModels.value = modelData as ModelConfig[]
    const activeIds = asrModels.value.filter((model) => model.status === 'active').map((model) => model.id)
    if (!selectedModelIds.value.length) {
      selectedModelIds.value = activeIds.slice(0, 4)
      baselineModelId.value = selectedModelIds.value[0]
    }
    await loadAsrResults()
  } finally {
    loading.value = false
  }
}

async function loadAsrResults() {
  const ids = filteredRecords.value.map((record) => record.id)
  if (!ids.length) {
    asrResultsByRecord.value = {}
    return
  }
  const data = await patientApi.listAsrResultsBatch(ids) as Record<string, AsrResult[]>
  const next: Record<string, Record<string, AsrResult>> = {}
  ids.forEach((id) => { next[String(id)] = {} })

  Object.entries(data || {}).forEach(([recordId, rows]) => {
    const grouped: Record<string, AsrResult[]> = {}
    ;(rows || []).forEach((row) => {
      const key = String(row.asr_model_id)
      grouped[key] = grouped[key] || []
      grouped[key].push(row)
    })
    next[recordId] = next[recordId] || {}
    Object.entries(grouped).forEach(([modelId, modelRows]) => {
      next[recordId][modelId] = pickDisplayResult(modelRows)
    })
  })
  asrResultsByRecord.value = next
}

function pickDisplayResult(rows: AsrResult[]) {
  const sorted = [...rows].sort(compareAsrResultDesc)
  return sorted.find((row) => isSuccessResult(row)) || sorted[0]
}

function compareAsrResultDesc(a: AsrResult, b: AsrResult) {
  const ta = a.created_at ? new Date(a.created_at).getTime() : 0
  const tb = b.created_at ? new Date(b.created_at).getTime() : 0
  if (ta !== tb) return tb - ta
  return (b.id || 0) - (a.id || 0)
}

function getCellResult(record: PatientExamination, modelId: number | null | undefined): AsrResult | null {
  if (!modelId) return null
  return asrResultsByRecord.value[String(record.id)]?.[String(modelId)] || null
}

function isSuccessResult(result?: AsrResult | null) {
  return !!result && result.status === 'success' && !!String(result.full_transcript || '').trim()
}

function getModel(modelId: number | null | undefined) {
  if (!modelId) return undefined
  return asrModels.value.find((model) => model.id === modelId)
}

function getModelName(modelId: number) {
  return getModel(modelId)?.name || `模型 ${modelId}`
}

function modelConfigSummary(model?: ModelConfig) {
  if (!model) return '-'
  const params = model.params || {}
  const parts = [
    params.audio_input_mode ? `音频:${audioModeText(params.audio_input_mode)}` : '',
    params.boosting_table_id || params.boosting_table_name ? '平台热词' : '',
    params.correct_table_id || params.correct_table_name ? '替换词表' : '',
    Array.isArray(params.hotwords) && params.hotwords.length ? `上下文热词:${params.hotwords.length}` : '',
    params.enable_ddc ? '顺滑' : '',
    params.stream ? 'stream' : '',
  ].filter(Boolean)
  return parts.length ? parts.join(' / ') : model.provider
}

function audioModeText(value: string) {
  if (value === 'segments') return '分段'
  if (value === 'grouped') return '分组合并'
  if (value === 'merged') return '整段'
  return value
}

function normalizeTranscript(text: string) {
  return String(text || '').replace(/\s+/g, ' ').trim()
}

function extractMedicalNumbers(text: string) {
  const matches = normalizeTranscript(text).match(/\d+(?:\.\d+)?/g) || []
  return matches.map((item) => Number(item).toFixed(item.includes('.') ? 1 : 0))
}

function diffNumbers(base: string[], current: string[]) {
  const currentCounts = countItems(current)
  const baseCounts = countItems(base)
  const missing: string[] = []
  const extra: string[] = []

  Object.entries(baseCounts).forEach(([value, count]) => {
    const delta = count - (currentCounts[value] || 0)
    for (let i = 0; i < delta; i += 1) missing.push(value)
  })
  Object.entries(currentCounts).forEach(([value, count]) => {
    const delta = count - (baseCounts[value] || 0)
    for (let i = 0; i < delta; i += 1) extra.push(value)
  })
  return { missing, extra }
}

function countItems(items: string[]) {
  return items.reduce<Record<string, number>>((acc, item) => {
    acc[item] = (acc[item] || 0) + 1
    return acc
  }, {})
}

function textDiff(baseText: string, currentText: string) {
  if (!baseText && !currentText) return { rate: 0, changed: false }
  if (baseText === currentText) return { rate: 0, changed: false }
  const base = baseText.slice(0, 4000)
  const current = currentText.slice(0, 4000)
  const maxLen = Math.max(base.length, current.length, 1)
  const distance = levenshtein(base, current)
  const tailPenalty = Math.abs(baseText.length - currentText.length) / Math.max(baseText.length, currentText.length, 1)
  const rate = Math.min(1, distance / maxLen + tailPenalty * 0.2)
  return { rate, changed: rate > 0.005 }
}

function levenshtein(a: string, b: string) {
  const n = a.length
  const m = b.length
  if (n === 0) return m
  if (m === 0) return n
  let prev = new Array(m + 1)
  let curr = new Array(m + 1)
  for (let j = 0; j <= m; j += 1) prev[j] = j
  for (let i = 1; i <= n; i += 1) {
    curr[0] = i
    for (let j = 1; j <= m; j += 1) {
      const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
    }
    ;[prev, curr] = [curr, prev]
  }
  return prev[m]
}

function compactNumbers(items: string[]) {
  const counts = countItems(items)
  return Object.entries(counts).map(([value, count]) => `${value}*${count}`).join('；')
}

function statusColor(status?: string) {
  if (status === 'success') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'running') return 'processing'
  if (status === 'missing') return 'default'
  return 'default'
}

function statusText(status?: string) {
  if (status === 'success') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'running') return '进行中'
  if (status === 'missing') return '未转写'
  return status || '未知'
}

function formatPercent(value: number) {
  if (!Number.isFinite(value)) return '-'
  return `${(value * 100).toFixed(1)}%`
}

function onSelectRows(keys: (string | number)[]) {
  selectedRowKeys.value = keys
}

function openDetail(row: EvalRow) {
  detailRow.value = row
  detailOpen.value = true
}

async function runBatch(mode: 'missing' | 'force') {
  const targetRows = mode === 'force'
    ? selectedEvalRows.value
    : evaluationRows.value.filter((row) => row.status === 'missing')

  if (!targetRows.length) {
    message.warning(mode === 'force' ? '请先勾选需要重跑的 ASR 变体' : '当前没有未转写任务')
    return
  }

  if (mode === 'force') {
    const confirmed = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: '确认重跑选中 ASR 变体？',
        content: `将重新调用 ${targetRows.length} 个 ASR 任务，历史结果会保留，页面展示最新成功结果。`,
        okText: '确认重跑',
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!confirmed) return
  }

  batchStats.value = { total: targetRows.length, done: 0, success: 0, skipped: 0, failed: 0, current: '' }
  batchRunning.value = true
  try {
    for (const row of targetRows) {
      const record = records.value.find((item) => item.id === row.patient_id)
      if (!record?.segs?.length) {
        batchStats.value.failed += 1
        batchStats.value.done += 1
        continue
      }
      batchStats.value.current = `${row.record_id} / ${row.model_name}`
      try {
        await runOneAsr(record, row.model_id)
        batchStats.value.success += 1
      } catch (error: any) {
        batchStats.value.failed += 1
        message.error(`${row.record_id} / ${row.model_name} 失败：${error?.message || error || '未知错误'}`)
      } finally {
        batchStats.value.done += 1
      }
    }
    await loadAsrResults()
    message.success('ASR 优化评估任务完成')
  } finally {
    batchRunning.value = false
  }
}

function runOneAsr(record: PatientExamination, modelId: number): Promise<AsrResult> {
  return new Promise((resolve, reject) => {
    let settled = false
    const es = patientApi.runAsrSSE(record.id, modelId)

    const finish = (fn: () => void) => {
      if (settled) return
      settled = true
      es.close()
      fn()
    }

    es.addEventListener('complete', (ev: MessageEvent) => {
      try {
        const parsed = JSON.parse(ev.data || '{}')
        finish(() => resolve(parsed as AsrResult))
      } catch (error) {
        finish(() => reject(error))
      }
    })

    es.addEventListener('error', (ev: any) => {
      if (settled) return
      if (ev?.data) {
        try {
          const parsed = JSON.parse(ev.data)
          finish(() => reject(new Error(parsed.message || 'ASR 调用失败')))
        } catch {
          finish(() => reject(new Error('ASR 调用失败')))
        }
      } else {
        finish(() => reject(new Error('ASR 连接中断')))
      }
    })
  })
}

function exportCsv() {
  if (!evaluationRows.value.length) {
    message.warning('当前没有可导出的评估数据')
    return
  }
  const lines: any[][] = []
  lines.push(['ASR优化评估总览'])
  lines.push(['ASR方案', '角色', '成功数', '失败数', '未转写', '发生变化数', '平均变化率', '漏识别数字数', '多识别数字数', '配置摘要'])
  modelSummaries.value.forEach((item) => {
    lines.push([
      item.modelName,
      item.modelId === baselineModelId.value ? '基线' : '变体',
      item.success,
      item.failed,
      item.missing,
      item.changed,
      formatPercent(item.averageChangeRate),
      item.missingNumbers,
      item.extraNumbers,
      item.configSummary,
    ])
  })
  lines.push([])
  lines.push(['评估明细'])
  lines.push(['病历号', '日期', 'ASR方案', '角色', '配置摘要', '状态', '是否变化', '变化率', '漏识别数字', '多识别数字', 'ASR全文', '错误信息'])
  evaluationRows.value.forEach((row) => {
    lines.push([
      row.record_id,
      row.date,
      row.model_name,
      row.is_baseline ? '基线' : '变体',
      row.config_summary,
      statusText(row.status),
      row.is_baseline ? '基线' : row.changed ? '有变化' : '无变化',
      row.is_baseline ? '-' : formatPercent(row.change_rate),
      compactNumbers(row.missing_numbers),
      compactNumbers(row.extra_numbers),
      row.transcript,
      row.error_message,
    ])
  })

  const csv = lines.map((row) => row.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const datePart = selectedDate.value === 'all' ? 'all' : selectedDate.value
  link.href = url
  link.download = `ASR优化评估_${datePart}_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  message.success('已导出 ASR 优化评估 CSV')
}

function csvCell(value: any) {
  const text = value === null || value === undefined ? '' : String(value)
  return `"${text.replace(/"/g, '""')}"`
}
</script>

<style scoped>
.asr-optimize-page {
  width: 100%;
  min-width: 0;
}
.page-card {
  width: 100%;
}
.sub-title {
  color: #888;
  font-size: 12px;
  font-weight: 400;
}
.tip {
  margin-bottom: 16px;
}
.filters {
  margin-bottom: 16px;
  padding: 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.label {
  color: #666;
}
.muted {
  color: #999;
}
.progress-card {
  margin-bottom: 16px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  min-width: 0;
}
.summary-title {
  margin-bottom: 8px;
  font-weight: 600;
}
.summary-line {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}
.summary-metric {
  color: #555;
  font-size: 12px;
  line-height: 1.7;
}
.summary-config {
  margin-top: 6px;
  color: #999;
  font-size: 12px;
  word-break: break-word;
}
.number-diff {
  color: #d46b08;
  font-size: 12px;
  line-height: 1.6;
}
.transcript-preview {
  max-height: 92px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  cursor: pointer;
  line-height: 1.6;
}
.transcript-preview:hover {
  color: #1677ff;
}
.config-text {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.transcript-box {
  min-height: 160px;
  max-height: 360px;
  overflow: auto;
  padding: 12px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
}
.transcript-box.baseline {
  background: #f6ffed;
}
</style>
