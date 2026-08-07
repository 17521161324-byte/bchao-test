<template>
  <aside class="debug-sidebar">
    <!-- 1. 标题 -->
    <div class="sb-title">ASR指纹与文本记录</div>

    <!-- 2. 指纹下拉 -->
    <a-select
      v-model:value="fingerprint"
      class="sb-fingerprint"
      :options="fingerprintOptions"
      @change="onFilterChange"
    />

    <!-- 3. 指纹信息卡（浅蓝渐变） -->
    <div class="sb-fp-card">
      <div class="fp-row">
        <span class="fp-value">{{ fingerprintLabel }}</span>
        <a-tag color="blue">{{ filteredRecords.length }} 条</a-tag>
      </div>
      <div class="fp-meta">来源：PatientAsrResult 历史结果</div>
      <div class="fp-meta">字段：config_hash + full_transcript</div>
    </div>

    <!-- 4. 筛选 -->
    <div class="sb-filters">
      <a-select v-model:value="date" class="sb-date" :options="dateOptions" placeholder="全部日期" allow-clear @change="onFilterChange" />
      <a-select v-model:value="statusFilter" class="sb-status" :options="statusOptions" @change="onFilterChange" />
      <a-input-search
        v-model:value="keyword"
        class="sb-search"
        placeholder="搜索结果ID、病历号或ASR文本"
        allow-clear
        @change="onFilterChange"
      />
    </div>

    <!-- 5. 批量工具栏（灰底圆角） -->
    <div class="sb-batch-bar">
      <a-checkbox :checked="allCurrentSelected" :indeterminate="partCurrentSelected" @change="toggleSelectAll">
        全选当前列表
      </a-checkbox>
      <span class="sb-selected-count">已选 {{ selectedKeys.length }} 条</span>
      <a-button size="small" type="primary" :disabled="!selectedKeys.length" :loading="batchRunning" @click="emitBatch">
        批量执行规则
      </a-button>
    </div>

    <!-- 6. 记录列表 -->
    <div class="sb-list" v-loading="loading">
      <div
        v-for="record in filteredRecords"
        :key="record.id"
        class="sb-item"
        :class="{ active: record.id === selectedId }"
        @click="onItemClick(record)"
      >
        <a-checkbox
          :checked="selectedKeys.includes(record.id)"
          @click.stop
          @change="toggleSelect(record)"
        />
        <div class="sb-item-body">
          <div class="sb-item-line1">
            <span class="sb-id">结果ID {{ record.id }}</span>
            <a-tag :color="statusTagColor[record.status]" class="sb-status-tag">{{ statusTagLabel[record.status] }}</a-tag>
          </div>
          <div class="sb-item-line2">{{ record.record_id || '-' }} · {{ record.date || '-' }}</div>
          <div class="sb-item-preview">{{ previewText(record.full_transcript) }}</div>
        </div>
      </div>
      <a-empty v-if="!loading && !filteredRecords.length" description="当前筛选条件下没有记录" :image-style="{ height: '48px' }" />
      <div v-if="!loading && records.length > filteredRecords.length" class="sb-filtered-note">
        已按筛选显示 {{ filteredRecords.length }} / {{ records.length }} 条
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SidebarRecord } from './debug'

const props = defineProps<{
  records: SidebarRecord[]
  selectedId: number | null
  loading?: boolean
  batchRunning?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', record: SidebarRecord): void
  (e: 'batch', ids: number[]): void
}>()

const fingerprint = ref('__ALL__')
const date = ref<string | undefined>()
const statusFilter = ref('all')
const keyword = ref('')
const selectedKeys = ref<number[]>([])

const statusTagColor: Record<string, string> = {
  pending: 'blue',
  review: 'orange',
  confirmed: 'green',
}
const statusTagLabel: Record<string, string> = {
  pending: '待处理',
  review: '需复核',
  confirmed: '已确认',
}
const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '待处理', value: 'pending' },
  { label: '需复核', value: 'review' },
  { label: '已确认', value: 'confirmed' },
]

const fingerprintOptions = computed(() => {
  const counts = new Map<string, number>()
  let emptyCount = 0
  props.records.forEach((row) => {
    const hash = String(row.config_hash || '').trim()
    if (!hash) {
      emptyCount += 1
      return
    }
    counts.set(hash, (counts.get(hash) || 0) + 1)
  })
  const options: { label: string; value: string }[] = [
    { label: `全部历史ASR指纹 · ${props.records.length}条文本`, value: '__ALL__' },
  ]
  Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .forEach(([hash, count]) => {
      options.push({ label: `${shortHash(hash)} · ${count}条历史文本`, value: hash })
    })
  if (emptyCount > 0) {
    options.push({ label: `无配置指纹 · ${emptyCount}条历史文本`, value: '__EMPTY__' })
  }
  return options
})

const dateOptions = computed(() => {
  const values = Array.from(new Set(props.records.map((row) => String(row.date || '').trim()).filter(Boolean)))
    .sort()
    .reverse()
  return values.map((value) => ({ label: value, value }))
})

const fingerprintLabel = computed(() => {
  if (fingerprint.value === '__ALL__') return '全部历史ASR指纹'
  if (fingerprint.value === '__EMPTY__') return '无配置指纹'
  return shortHash(fingerprint.value)
})

const filteredRecords = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return props.records.filter((row) => {
    if (fingerprint.value === '__EMPTY__') {
      if (String(row.config_hash || '').trim()) return false
    } else if (fingerprint.value !== '__ALL__' && String(row.config_hash || '') !== fingerprint.value) {
      return false
    }
    if (date.value && String(row.date || '') !== date.value) return false
    if (statusFilter.value !== 'all' && row.status !== statusFilter.value) return false
    if (q) {
      const haystack = `${row.id} ${row.record_id || ''} ${row.full_transcript || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    return true
  })
})

const filteredIds = computed(() => filteredRecords.value.map((row) => row.id))
const allCurrentSelected = computed(() =>
  filteredIds.value.length > 0 && filteredIds.value.every((id) => selectedKeys.value.includes(id))
)
const partCurrentSelected = computed(() => {
  const inList = filteredIds.value.filter((id) => selectedKeys.value.includes(id)).length
  return inList > 0 && !allCurrentSelected.value
})

function onFilterChange() {
  // 筛选变化后仅保留仍在当前列表内的选择
  const keep = new Set(filteredIds.value)
  selectedKeys.value = selectedKeys.value.filter((id) => keep.has(id))
}

function toggleSelect(record: SidebarRecord) {
  const idx = selectedKeys.value.indexOf(record.id)
  if (idx >= 0) selectedKeys.value.splice(idx, 1)
  else selectedKeys.value.push(record.id)
}

function toggleSelectAll(event: any) {
  if (event?.target?.checked) {
    const keep = new Set(selectedKeys.value)
    filteredIds.value.forEach((id) => keep.add(id))
    selectedKeys.value = Array.from(keep)
  } else {
    const drop = new Set(filteredIds.value)
    selectedKeys.value = selectedKeys.value.filter((id) => !drop.has(id))
  }
}

function onItemClick(record: SidebarRecord) {
  emit('select', record)
}

function emitBatch() {
  emit('batch', selectedKeys.value)
}

function previewText(text?: string) {
  const value = String(text || '').trim()
  if (!value) return '（无ASR文本）'
  return value.split('\n').slice(0, 2).join('\n')
}

function shortHash(value: string) {
  if (!value) return '-'
  return value.length > 18 ? `${value.slice(0, 16)}…` : value
}
</script>

<style scoped>
.debug-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: #fff;
  border-right: 1px solid #ebeef5;
  padding: 14px 12px;
  gap: 10px;
}
.sb-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2329;
}
.sb-fingerprint { width: 100%; }
.sb-fp-card {
  background: linear-gradient(135deg, #f0f7ff 0%, #e8f4fd 100%);
  border: 1px solid #d6e8fa;
  border-radius: 8px;
  padding: 10px 12px;
  display: grid;
  gap: 4px;
}
.fp-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.fp-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: #1664a0;
  word-break: break-all;
}
.fp-meta { font-size: 12px; color: #5c6b7a; }
.sb-filters { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.sb-date, .sb-status { width: 100%; }
.sb-search { grid-column: 1 / -1; width: 100%; }
.sb-batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f5f6f8;
  border-radius: 8px;
  padding: 8px 10px;
  flex-wrap: wrap;
}
.sb-selected-count { color: #5c6b7a; font-size: 12px; margin-left: auto; }
.sb-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 -4px;
  padding: 0 4px;
}
.sb-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
  position: relative;
  transition: background 0.15s, border-color 0.15s;
}
.sb-item:hover { background: #f7f9fc; }
.sb-item.active {
  background: #eaf4ff;
  border-color: #91caff;
}
.sb-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 2px;
  background: #409eff;
}
.sb-item-body { min-width: 0; flex: 1; display: grid; gap: 2px; }
.sb-item-line1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sb-id { font-weight: 600; font-size: 13px; color: #1f2329; }
.sb-status-tag { margin-inline-end: 0; }
.sb-item-line2 { font-size: 12px; color: #5c6b7a; }
.sb-item-preview {
  font-size: 12px;
  color: #7a8494;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sb-filtered-note { text-align: center; color: #a0a8b4; font-size: 12px; padding: 6px 0; }
</style>
