<template>
  <div class="asr-compare-page">
    <a-card class="page-card">
      <template #title>
        <a-space direction="vertical" :size="2">
          <span>ASR 模型对比</span>
          <span class="sub-title">按检查记录横向对比不同 ASR 模型的转写结果，并支持批量补齐或重新调用</span>
        </a-space>
      </template>
      <template #extra>
        <a-space>
          <a-button @click="loadAll" :loading="loading">刷新</a-button>
          <a-button :disabled="!canExport" @click="exportComparison">
            导出当前对比
          </a-button>
          <a-button type="primary" :disabled="!canRunBatch" :loading="batchRunning" @click="runBatch('reuse')">
            补齐未转写
          </a-button>
          <a-button danger :disabled="!canForceRun" :loading="batchRunning" @click="runBatch('force')">
            重跑选中行
          </a-button>
        </a-space>
      </template>

      <a-alert
        class="tip"
        type="info"
        show-icon
        :message="selectionTip"
      />

      <div class="filters">
        <a-space wrap>
          <span class="label">批次</span>
          <a-select v-model:value="selectedDate" style="width: 180px" :options="dateOptions" @change="loadAsrResults" />

          <span class="label">ASR 模型</span>
          <a-select
            v-model:value="selectedModelIds"
            mode="multiple"
            style="min-width: 360px"
            :max-tag-count="3"
            :options="modelOptions"
            placeholder="请选择 ASR 模型"
          />

          <a-input-search
            v-model:value="keyword"
            allow-clear
            style="width: 220px"
            placeholder="搜索病历号"
          />
        </a-space>
      </div>

      <a-card v-if="batchRunning || batchStats.total > 0" size="small" class="progress-card">
        <a-space direction="vertical" style="width: 100%">
          <a-space wrap>
            <a-tag color="blue">总任务 {{ batchStats.total }}</a-tag>
            <a-tag color="green">成功 {{ batchStats.success }}</a-tag>
            <a-tag color="default">复用 {{ batchStats.skipped }}</a-tag>
            <a-tag color="red">失败 {{ batchStats.failed }}</a-tag>
            <span class="muted">{{ batchStats.current || '等待执行' }}</span>
          </a-space>
          <a-progress :percent="batchPercent" size="small" />
        </a-space>
      </a-card>

      <a-table
        :columns="columns"
        :data-source="filteredRecords"
        :loading="loading"
        :pagination="{ pageSize: 20, showSizeChanger: true }"
        :row-selection="{ selectedRowKeys, onChange: onSelectRows }"
        :scroll="{ x: 'max-content' }"
        row-key="id"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'audio'">
            <a-tag :color="record.segs?.length ? 'green' : 'default'">
              {{ record.segs?.length || 0 }} 段
            </a-tag>
          </template>

          <template v-else-if="isModelColumn(column.key)">
            <div
              class="asr-cell"
              :class="{ clickable: !!getCellResult(record, getModelIdFromColumn(column.key)) }"
              @click="openResult(record, getModelIdFromColumn(column.key))"
            >
              <template v-if="isCellRunning(record.id, getModelIdFromColumn(column.key))">
                <a-tag color="processing">识别中</a-tag>
                <div class="cell-text muted">正在调用模型...</div>
              </template>
              <template v-else-if="getCellResult(record, getModelIdFromColumn(column.key))">
                <a-tag :color="statusColor(getCellResult(record, getModelIdFromColumn(column.key))?.status)">
                  {{ statusText(getCellResult(record, getModelIdFromColumn(column.key))?.status) }}
                </a-tag>
                <div class="cell-text">
                  {{ transcriptText(getCellResult(record, getModelIdFromColumn(column.key))) }}
                </div>
              </template>
              <template v-else>
                <a-tag color="default">未转写</a-tag>
                <div class="cell-text muted">暂无结果</div>
              </template>
            </div>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="detailOpen"
      width="920px"
      :title="detailTitle"
      :footer="null"
    >
      <template v-if="detailResult">
        <a-descriptions size="small" bordered :column="2">
          <a-descriptions-item label="状态">
            <a-tag :color="statusColor(detailResult.status)">{{ statusText(detailResult.status) }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="执行时间">{{ formatTime(detailResult.created_at) }}</a-descriptions-item>
          <a-descriptions-item label="Provider">{{ detailResult.provider || '-' }}</a-descriptions-item>
          <a-descriptions-item label="错误">{{ detailResult.error_message || '-' }}</a-descriptions-item>
        </a-descriptions>

        <a-divider orientation="left">完整转写</a-divider>
        <div class="transcript-box">
          {{ detailResult.full_transcript || '暂无转写文本' }}
        </div>

        <a-divider orientation="left">分段结果</a-divider>
        <a-table
          size="small"
          :pagination="false"
          :columns="segmentColumns"
          :data-source="detailSegments"
          row-key="seg_index"
        />
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
  exam_record_id?: number
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

const loading = ref(false)
const batchRunning = ref(false)
const records = ref<PatientExamination[]>([])
const asrModels = ref<ModelConfig[]>([])
const selectedDate = ref<string>('all')
const selectedModelIds = ref<number[]>([])
const keyword = ref('')
const asrResultsByRecord = ref<Record<string, Record<string, AsrResult>>>({})
const runningCells = ref<Set<string>>(new Set())
const selectedRowKeys = ref<number[]>([])

const detailOpen = ref(false)
const detailRecord = ref<PatientExamination | null>(null)
const detailModelId = ref<number | null>(null)
const detailResult = ref<AsrResult | null>(null)

const batchStats = ref({
  total: 0,
  done: 0,
  success: 0,
  skipped: 0,
  failed: 0,
  current: '',
})

const segmentColumns = [
  { title: '分段', dataIndex: 'seg_index', key: 'seg_index', width: 80 },
  { title: '时长', dataIndex: 'duration', key: 'duration', width: 100 },
  { title: '转写文本', dataIndex: 'text', key: 'text' },
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
    label: `${model.name}${model.status === 'active' ? '' : '（未启用）'}`,
    value: model.id,
    disabled: model.status !== 'active',
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

const columns = computed(() => {
  const base = [
    { title: '病历号', dataIndex: 'record_id', key: 'record_id', fixed: 'left', width: 105 },
    { title: '日期', dataIndex: 'date', key: 'date', width: 105 },
    { title: '录音', key: 'audio', width: 72 },
  ]
  const modelCols = selectedModelIds.value.map((modelId) => ({
    title: getModelName(modelId),
    key: modelColumnKey(modelId),
    width: 560,
  }))
  return [...base, ...modelCols]
})

const canRunBatch = computed(() =>
  selectedModelIds.value.length > 0 && filteredRecords.value.length > 0 && !batchRunning.value,
)

const selectedRecords = computed(() => {
  const selected = new Set(selectedRowKeys.value)
  return filteredRecords.value.filter((record) => selected.has(record.id))
})

const canForceRun = computed(() =>
  selectedModelIds.value.length > 0 && selectedRecords.value.length > 0 && !batchRunning.value,
)

const canExport = computed(() => filteredRecords.value.length > 0 && selectedModelIds.value.length > 0)

const selectionTip = computed(() => {
  const selectedCount = selectedRecords.value.length
  return `补齐未转写会复用已成功的 ASR 结果；重跑只处理已勾选的检查记录和已选择的 ASR 模型。当前已选 ${selectedCount} 行。`
})

const batchPercent = computed(() => {
  if (!batchStats.value.total) return 0
  return Math.round((batchStats.value.done / batchStats.value.total) * 100)
})

const detailTitle = computed(() => {
  const record = detailRecord.value
  const modelName = detailModelId.value ? getModelName(detailModelId.value) : ''
  return record ? `${record.record_id} / ${record.date} / ${modelName}` : 'ASR 结果'
})

const detailSegments = computed(() => {
  const segments = detailResult.value?.segments
  return Array.isArray(segments) ? segments : []
})

watch(selectedModelIds, () => {
  if (detailOpen.value && detailRecord.value && detailModelId.value) {
    detailResult.value = getCellResult(detailRecord.value, detailModelId.value)
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
      selectedModelIds.value = activeIds
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

function getCellResult(record: PatientExamination, modelId: number | null): AsrResult | null {
  if (!modelId) return null
  return asrResultsByRecord.value[String(record.id)]?.[String(modelId)] || null
}

function isSuccessResult(result?: AsrResult | null) {
  return !!result && result.status === 'success' && !!String(result.full_transcript || '').trim()
}

function getModelName(modelId: number) {
  return asrModels.value.find((model) => model.id === modelId)?.name || `模型 ${modelId}`
}

function modelColumnKey(modelId: number) {
  return `asr_model_${modelId}`
}

function isModelColumn(key: string) {
  return String(key || '').startsWith('asr_model_')
}

function getModelIdFromColumn(key: string) {
  return Number(String(key || '').replace('asr_model_', '')) || null
}

function cellKey(recordId: number, modelId: number) {
  return `${recordId}:${modelId}`
}

function isCellRunning(recordId: number, modelId: number | null) {
  return !!modelId && runningCells.value.has(cellKey(recordId, modelId))
}

function setCellRunning(recordId: number, modelId: number, running: boolean) {
  const next = new Set(runningCells.value)
  const key = cellKey(recordId, modelId)
  if (running) next.add(key)
  else next.delete(key)
  runningCells.value = next
}

function statusColor(status?: string) {
  if (status === 'success') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'running') return 'processing'
  return 'default'
}

function statusText(status?: string) {
  if (status === 'success') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'running') return '进行中'
  return status || '未知'
}

function transcriptText(result?: AsrResult | null) {
  if (!result) return '暂无结果'
  return result.full_transcript || result.error_message || '暂无文本'
}

function formatTime(value?: string) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 19)
}

function openResult(record: PatientExamination, modelId: number | null) {
  if (!modelId) return
  const result = getCellResult(record, modelId)
  if (!result) return
  detailRecord.value = record
  detailModelId.value = modelId
  detailResult.value = result
  detailOpen.value = true
}

function updateResult(recordId: number, result: AsrResult) {
  const next = { ...asrResultsByRecord.value }
  const row = { ...(next[String(recordId)] || {}) }
  row[String(result.asr_model_id)] = result
  next[String(recordId)] = row
  asrResultsByRecord.value = next
}

async function runBatch(mode: 'reuse' | 'force') {
  if (!selectedModelIds.value.length) {
    message.warning('请先选择 ASR 模型')
    return
  }
  if (!filteredRecords.value.length) {
    message.warning('当前筛选范围没有检查记录')
    return
  }
  const targetRecords = mode === 'force' ? selectedRecords.value : filteredRecords.value
  if (!targetRecords.length) {
    message.warning(mode === 'force' ? '请先勾选需要重跑的检查记录' : '当前没有可执行的检查记录')
    return
  }

  if (mode === 'force') {
    const confirmed = await new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: '确认重跑选中行？',
        content: `这会对已勾选的 ${targetRecords.length} 条检查记录，使用已选择的 ${selectedModelIds.value.length} 个 ASR 模型重新发起调用。历史结果会保留，最新结果会用于展示。`,
        okText: '确认重跑',
        cancelText: '取消',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!confirmed) return
  }

  const tasks: Array<{ record: PatientExamination; modelId: number; reuse: boolean }> = []
  targetRecords.forEach((record) => {
    selectedModelIds.value.forEach((modelId) => {
      const existing = getCellResult(record, modelId)
      const reuse = mode === 'reuse' && isSuccessResult(existing)
      tasks.push({ record, modelId, reuse })
    })
  })

  batchStats.value = { total: tasks.length, done: 0, success: 0, skipped: 0, failed: 0, current: '' }
  batchRunning.value = true
  try {
    for (const task of tasks) {
      const modelName = getModelName(task.modelId)
      batchStats.value.current = `${task.record.record_id} / ${modelName}`

      if (task.reuse) {
        batchStats.value.skipped += 1
        batchStats.value.done += 1
        continue
      }

      if (!task.record.segs?.length) {
        batchStats.value.failed += 1
        batchStats.value.done += 1
        continue
      }

      try {
        setCellRunning(task.record.id, task.modelId, true)
        const result = await runOneAsr(task.record, task.modelId)
        updateResult(task.record.id, result)
        batchStats.value.success += 1
      } catch (error: any) {
        batchStats.value.failed += 1
        message.error(`${task.record.record_id} / ${modelName} 失败：${error?.message || error || '未知错误'}`)
      } finally {
        setCellRunning(task.record.id, task.modelId, false)
        batchStats.value.done += 1
      }
    }

    await loadAsrResults()
    message.success('ASR 对比批量任务完成')
  } finally {
    batchRunning.value = false
  }
}

function onSelectRows(keys: (string | number)[]) {
  selectedRowKeys.value = keys.map((key) => Number(key)).filter((key) => Number.isFinite(key))
}

function exportComparison() {
  const rows = filteredRecords.value
  if (!rows.length || !selectedModelIds.value.length) {
    message.warning('当前没有可导出的对比数据')
    return
  }

  const headers = ['病历号', '日期', '录音段数']
  selectedModelIds.value.forEach((modelId) => {
    const modelName = getModelName(modelId)
    headers.push(`${modelName}-状态`, `${modelName}-转写全文`, `${modelName}-执行时间`, `${modelName}-错误信息`)
  })

  const body = rows.map((record) => {
    const line: any[] = [
      record.record_id,
      record.date,
      record.segs?.length || 0,
    ]
    selectedModelIds.value.forEach((modelId) => {
      const result = getCellResult(record, modelId)
      line.push(
        statusText(result?.status),
        transcriptText(result),
        formatTime(result?.created_at),
        result?.error_message || '',
      )
    })
    return line
  })

  const csv = [headers, ...body].map((row) => row.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const datePart = selectedDate.value === 'all' ? 'all' : selectedDate.value
  link.href = url
  link.download = `ASR模型对比_${datePart}_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
  message.success('已导出当前 ASR 对比表')
}

function csvCell(value: any) {
  const text = value === null || value === undefined ? '' : String(value)
  return `"${text.replace(/"/g, '""')}"`
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
</script>

<style scoped>
.asr-compare-page {
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

.progress-card {
  margin-bottom: 16px;
}

.label {
  color: #666;
}

.muted {
  color: #999;
}

.asr-cell {
  min-width: 240px;
  max-width: 360px;
}

.asr-cell.clickable {
  cursor: pointer;
}

.asr-cell.clickable:hover .cell-text {
  color: #1677ff;
}

.cell-text {
  margin-top: 6px;
  line-height: 1.5;
  white-space: normal;
  word-break: break-all;
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
</style>
