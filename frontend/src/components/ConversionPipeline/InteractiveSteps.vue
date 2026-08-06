<template>
  <section class="interactive-steps panel">
    <div class="steps-track">
      <div
        v-for="node in nodes"
        :key="node.step_code"
        class="step-node"
        :class="[`status-${node.status}`, { current: node.step_code === currentStepCode, clickable: !disabled }]"
        @click="onNodeClick(node)"
      >
        <div class="step-badge">
          <span class="step-index">{{ node.step_order / 10 }}</span>
          <span v-if="node.status === 'running'" class="step-status-spin" />
          <span v-else class="step-status-dot" />
        </div>
        <div class="step-name">{{ node.step_name }}</div>
        <div class="step-summary">{{ node.summary }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineStep, PipelineStepStatus } from '@/types/conversionPipeline'

const props = defineProps<{
  steps: PipelineStep[]
  currentStepCode?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', step: PipelineStep): void
}>()

/** 七步固定定义（对应后端 STEP_NAMES 简称，实施说明 §7.1） */
const DEFAULT_STEPS = [
  { step_code: 'BASE_CLEANING', step_name: '基础清洗', step_order: 10 },
  { step_code: 'NUMBER_NORMALIZE', step_name: '数字与尺寸', step_order: 20 },
  { step_code: 'MEDICAL_TERM', step_name: '医学词处理', step_order: 30 },
  { step_code: 'BUSINESS_SEGMENT', step_name: '业务片段', step_order: 40 },
  { step_code: 'FIELD_PARSE', step_name: '字段解析', step_order: 50 },
  { step_code: 'RUNTIME_RULE', step_name: '参数规则', step_order: 60 },
  { step_code: 'RISK_INTERCEPT', step_name: '风险分流', step_order: 70 },
]

interface StepNode {
  step_code: string
  step_name: string
  step_order: number
  status: PipelineStepStatus
  summary: string
}

const statusMap: Record<string, PipelineStepStatus> = {
  pending: 'pending',
  running: 'running',
  success: 'success',
  warning: 'warning',
  failed: 'failed',
  manual_edited: 'manual_edited',
  dirty: 'dirty',
}

function stepSummary(step: PipelineStep | undefined): string {
  if (!step) return '待执行'
  switch (step.status) {
    case 'running':
      return '执行中…'
    case 'failed':
      return '失败'
    case 'manual_edited':
      return '已人工修改'
    case 'dirty':
      return '上游已改，需重跑'
    case 'pending':
      return '待执行'
    default: {
      const parts: string[] = []
      if ((step.rule_hits || []).length) parts.push(`命中 ${step.rule_hits.length}`)
      if ((step.warnings || []).length) parts.push(`警示 ${step.warnings.length}`)
      const changedCount = countChangedFields(step)
      if (changedCount > 0) parts.push(`字段 ${changedCount}`)
      if (step.status === 'warning' && !parts.length) parts.push('需复核')
      if (step.duration_ms > 0) parts.push(`${(step.duration_ms / 1000).toFixed(1)}s`)
      return parts.join(' · ') || '完成'
    }
  }
}

/** 状态机变化字段数（state_before → state_after 值不同的 key） */
function countChangedFields(step: PipelineStep): number {
  const before = step.state_before || {}
  const after = step.state_after || {}
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))
  return keys.filter((key) => formatValue(before[key]) !== formatValue(after[key])).length
}

function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const nodes = computed<StepNode[]>(() => {
  const byCode = new Map<string, PipelineStep>()
  ;(props.steps || []).forEach((step) => byCode.set(step.step_code, step))
  return DEFAULT_STEPS.map((def) => {
    const step = byCode.get(def.step_code)
    return {
      ...def,
      status: statusMap[step?.status || 'pending'] || 'pending',
      summary: stepSummary(step),
    }
  })
})

function onNodeClick(node: StepNode) {
  if (props.disabled) return
  const step = (props.steps || []).find((item) => item.step_code === node.step_code)
  emit('select', step || { ...node, input_text: '', output_text: '', conversions: [], rule_hits: [], warnings: [], state_before: {}, state_after: {}, fields: {}, source_spans: [], duration_ms: 0, config_hash: '' })
}
</script>

<style scoped>
.interactive-steps { padding: 14px 12px; }
.steps-track {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
}
.step-node {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 4px;
  border-radius: 8px;
  cursor: default;
  transition: background 0.2s;
  min-width: 0;
}
.step-node.clickable { cursor: pointer; }
.step-node.clickable:hover { background: #f5f5f5; }
.step-node.current { background: #e6f4ff; box-shadow: inset 0 0 0 1px #91caff; }
.step-badge {
  position: relative;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.step-index { position: relative; z-index: 1; }
.step-status-spin {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid rgba(22, 119, 255, 0.3);
  border-top-color: #1677ff;
  animation: step-spin 0.9s linear infinite;
}
.step-status-dot {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  right: -2px;
  bottom: -2px;
  border: 1.5px solid #fff;
}
.step-name {
  font-size: 12.5px;
  font-weight: 500;
  text-align: center;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.step-summary {
  font-size: 11px;
  color: #888;
  text-align: center;
  line-height: 1.3;
  min-height: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
/* 状态配色：pending 灰 / running 蓝 / success 绿 / warning 橙 / failed 红 / manual_edited 紫 / dirty 深橙 */
.status-pending .step-badge { background: #bfbfbf; }
.status-running .step-badge { background: #1677ff; }
.status-running .step-status-spin { animation-name: step-spin; }
.status-success .step-badge { background: #52c41a; }
.status-warning .step-badge { background: #fa8c16; }
.status-failed .step-badge { background: #ff4d4f; }
.status-failed .step-name { color: #ff4d4f; }
.status-manual_edited .step-badge { background: #722ed1; }
.status-manual_edited .step-name { color: #722ed1; }
.status-dirty .step-badge { background: #d46b08; }
.status-dirty .step-name { color: #d46b08; }
@keyframes step-spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1100px) {
  .steps-track { grid-template-columns: repeat(7, minmax(0, 1fr)); overflow-x: auto; }
}
</style>
