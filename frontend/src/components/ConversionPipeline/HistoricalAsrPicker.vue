<template>
  <div class="historical-asr-picker">
    <div class="filters">
      <a-select
        v-model:value="fingerprint"
        :options="fingerprintOptions"
        class="fingerprint-select"
        placeholder="历史ASR指纹"
      />
      <a-select v-model:value="date" :options="dateOptions" allow-clear placeholder="日期" class="date-select" />
      <a-input-search v-model:value="keyword" allow-clear placeholder="搜索病历号 / ASR结果ID" class="search-input" />
      <a-button size="small" :loading="loading" @click="load">刷新真实数据</a-button>
    </div>

    <div class="summary">
      <span>历史ASR指纹来自 <code>PatientAsrResult.config_hash</code></span>
      <span>当前筛选 {{ filteredRows.length }} 条 / 共 {{ rows.length }} 条 · 已选 {{ selectedRowKeys.length }} 条</span>
    </div>

    <a-table
      size="small"
      row-key="id"
      :columns="columns"
      :data-source="filteredRows"
      :loading="loading"
      :pagination="{ pageSize: 8, showSizeChanger: false }"
      :custom-row="rowProps"
      :row-selection="rowSelection"
      class="history-table"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'config_hash'">
          <code class="hash">{{ shortHash(record.config_hash) }}</code>
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tag :color="record.status === 'success' ? 'green' : record.status === 'partial' ? 'orange' : 'default'">
            {{ record.status || '-' }}
          </a-tag>
        </template>
      </template>
    </a-table>

    <div v-if="activeRow" class="selected-card">
      <div class="selected-head">
        <a-space wrap>
          <a-tag color="blue">ASR结果ID {{ activeRow.id }}</a-tag>
          <a-tag>{{ activeRow.record_id || '-' }}</a-tag>
          <a-tag>{{ activeRow.date || '-' }}</a-tag>
          <a-tag>{{ activeRow.model_name || '-' }}</a-tag>
          <code>{{ activeRow.config_hash || '无config_hash' }}</code>
        </a-space>
      </div>
      <pre class="preview">{{ activeRow.full_transcript || '-' }}</pre>
    </div>

    <a-empty v-else-if="!loading" description="请选择一条真实历史ASR结果" :image-style="{ height: '48px' }" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { audioApi, patientApi } from '@/api/client'

const emit = defineEmits<{
  (e: 'select', row: Record<string, any> | null): void
  (e: 'selection-change', rows: Record<string, any>[]): void
}>()

const loading = ref(false)
const rows = ref<Record<string, any>[]>([])
const activeRow = ref<Record<string, any> | null>(null)
const selectedRowKeys = ref<number[]>([])
const fingerprint = ref('__ALL__')
const date = ref<string | undefined>()
const keyword = ref('')

const columns = [
  { title: 'ASR结果ID', dataIndex: 'id', key: 'id', width: 92 },
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', width: 112 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 96 },
  { title: 'ASR方案', dataIndex: 'model_name', key: 'model_name', width: 170, ellipsis: true },
  { title: '指纹', key: 'config_hash', width: 150 },
  { title: '状态', key: 'status', width: 86 },
]

const fingerprintOptions = computed(() => {
  const counts = new Map<string, number>()
  rows.value.forEach((row) => {
    const hash = String(row.config_hash || '')
    if (!hash) return
    counts.set(hash, (counts.get(hash) || 0) + 1)
  })
  return [
    { label: `全部历史ASR指纹 · ${rows.value.length}条`, value: '__ALL__' },
    ...Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([hash, count]) => ({ label: `${shortHash(hash)} · ${count}条`, value: hash })),
  ]
})

const dateOptions = computed(() => {
  const values = Array.from(new Set(rows.value.map((row) => String(row.date || '')).filter(Boolean))).sort().reverse()
  return values.map((value) => ({ label: value, value }))
})

const filteredRows = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return rows.value.filter((row) => {
    if (fingerprint.value !== '__ALL__' && row.config_hash !== fingerprint.value) return false
    if (date.value && String(row.date || '') !== date.value) return false
    if (q) {
      const haystack = `${row.id} ${row.record_id || ''} ${row.model_name || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    return true
  })
})

const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  preserveSelectedRowKeys: true,
  onChange: (keys: (string | number)[]) => {
    selectedRowKeys.value = keys.map((key) => Number(key)).filter(Number.isFinite)
    emitSelection()
  },
}))

function emitSelection() {
  const keySet = new Set(selectedRowKeys.value)
  emit('selection-change', rows.value.filter((row) => keySet.has(Number(row.id))))
}

function shortHash(value: string | null | undefined) {
  if (!value) return '-'
  return value.length > 18 ? `${value.slice(0, 16)}…` : value
}

function rowProps(record: Record<string, any>) {
  return {
    onClick: () => {
      activeRow.value = record
      emit('select', record)
    },
    class: activeRow.value?.id === record.id ? 'selected-row' : '',
  }
}

async function load() {
  loading.value = true
  try {
    const records: any[] = (await audioApi.getRecords()) || []
    const ids = records.map((item: any) => Number(item.id)).filter((id: number) => Number.isFinite(id))
    const recordMap = new Map(records.map((item: any) => [Number(item.id), item]))
    const batches: number[][] = []
    for (let i = 0; i < ids.length; i += 100) batches.push(ids.slice(i, i + 100))

    const resultMap: Record<string, any[]> = {}
    for (const batch of batches) {
      const data: any = await patientApi.listAsrResultsBatch(batch)
      Object.assign(resultMap, data || {})
    }

    const flattened: Record<string, any>[] = []
    Object.entries(resultMap).forEach(([patientId, items]) => {
      const record = recordMap.get(Number(patientId)) || {}
      ;(items || []).forEach((item: any) => {
        if (!String(item.full_transcript || '').trim()) return
        flattened.push({
          ...item,
          exam_record_id: Number(patientId),
          record_id: item.record_id || record.record_id,
          date: item.date || record.date,
        })
      })
    })
    flattened.sort((a, b) => Number(b.id || 0) - Number(a.id || 0))
    rows.value = flattened

    const available = new Set(rows.value.map((row) => Number(row.id)))
    selectedRowKeys.value = selectedRowKeys.value.filter((id) => available.has(id))
    emitSelection()

    if (activeRow.value) {
      const refreshed = rows.value.find((row) => row.id === activeRow.value?.id) || null
      activeRow.value = refreshed
      emit('select', refreshed)
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.historical-asr-picker { display: grid; gap: 10px; }
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.fingerprint-select { width: 260px; }
.date-select { width: 130px; }
.search-input { width: 240px; }
.summary { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; color: #888; font-size: 12px; }
.history-table :deep(.ant-table-row) { cursor: pointer; }
.history-table :deep(.selected-row > td) { background: #e6f4ff !important; }
.hash { font-size: 12px; }
.selected-card { border: 1px solid #d9d9d9; border-radius: 6px; padding: 10px; background: #fafafa; }
.selected-head { margin-bottom: 8px; }
.preview { white-space: pre-wrap; word-break: break-word; max-height: 180px; overflow: auto; margin: 0; line-height: 1.7; font-family: inherit; }
</style>
