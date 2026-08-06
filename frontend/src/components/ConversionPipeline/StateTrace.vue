<template>
  <div class="state-trace">
    <div v-if="traceRows.length" class="trace-grid">
      <div class="trace-col">
        <div class="trace-title">执行前状态</div>
        <div v-if="beforeRows.length" class="trace-body">
          <div v-for="(row, idx) in beforeRows" :key="`b-${idx}`" class="trace-line">
            <span class="trace-key">{{ row.key }}</span>
            <span class="trace-value">{{ row.value }}</span>
          </div>
        </div>
        <span v-else class="muted">无状态</span>
      </div>
      <div class="trace-col">
        <div class="trace-title">执行后状态</div>
        <div v-if="afterRows.length" class="trace-body">
          <div v-for="(row, idx) in afterRows" :key="`a-${idx}`" class="trace-line">
            <span class="trace-key">{{ row.key }}</span>
            <span class="trace-value">{{ row.value }}</span>
            <a-tag v-if="row.changed" color="orange" class="changed-tag">变化</a-tag>
          </div>
        </div>
        <span v-else class="muted">无状态</span>
      </div>
    </div>
    <div v-else class="muted">本步骤无状态机变化</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineStep } from '@/types/conversionPipeline'

const props = defineProps<{
  step: PipelineStep
}>()

interface StateRow {
  key: string
  value: string
  changed: boolean
}

function toRows(state: Record<string, any>): StateRow[] {
  return Object.entries(state || {}).map(([key, value]) => ({
    key,
    value: formatValue(value),
    changed: false,
  }))
}

/** 合并前后状态所有 key，标记执行后发生变化（新增/删除/值不同）的 key */
const traceRows = computed<StateRow[][]>(() => {
  const before = props.step.state_before || {}
  const after = props.step.state_after || {}
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).sort()
  if (!keys.length) return []
  const beforeRows: StateRow[] = []
  const afterRows: StateRow[] = []
  for (const key of keys) {
    const beforeValue = formatValue(before[key])
    const afterValue = formatValue(after[key])
    const changed = beforeValue !== afterValue
    beforeRows.push({ key, value: beforeValue, changed })
    afterRows.push({ key, value: afterValue, changed })
  }
  return [beforeRows, afterRows]
})

const beforeRows = computed(() => traceRows.value[0] || [])
const afterRows = computed(() => traceRows.value[1] || [])

function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<style scoped>
.state-trace {
  display: grid;
  gap: 10px;
}
.trace-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.trace-col {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 8px 10px;
  min-width: 0;
}
.trace-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.trace-body {
  display: grid;
  gap: 3px;
  max-height: 260px;
  overflow: auto;
}
.trace-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}
.trace-key {
  color: #666;
  white-space: nowrap;
  font-family: inherit;
}
.trace-value {
  flex: 1;
}
.changed-tag {
  flex-shrink: 0;
}
.muted { color: #888; font-size: 12px; }
</style>
