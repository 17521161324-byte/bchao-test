<template>
  <section class="interactive-steps panel">
    <div class="steps-track">
      <div
        v-for="(node, index) in nodes"
        :key="node.business_code"
        class="step-node"
        :class="[`status-${node.status}`, { current: node.current, clickable: !disabled }]"
        @click="onNodeClick(node)"
      >
        <div class="step-badge">
          <span class="step-index">{{ index + 1 }}</span>
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

const BUSINESS_STEPS = [
  { business_code: 'MEDICAL_TERM', target: 'MEDICAL_TERM', step_name: '医学名词标准化', technical: ['MEDICAL_TERM'] },
  { business_code: 'BASE_CLEANING', target: 'BASE_CLEANING', step_name: '清洗与中文数值预处理', technical: ['BASE_CLEANING'] },
  { business_code: 'NUMBER_NORMALIZE', target: 'NUMBER_NORMALIZE', step_name: '数字与尺寸转换', technical: ['NUMBER_NORMALIZE'] },
  { business_code: 'BUSINESS_SEGMENT', target: 'BUSINESS_SEGMENT', step_name: '业务片段定位', technical: ['BUSINESS_SEGMENT'] },
  {
    business_code: 'FIELD_VALIDATE',
    target: 'RISK_INTERCEPT',
    step_name: '字段解析、校验与分流',
    technical: ['FIELD_PARSE', 'RUNTIME_RULE', 'RISK_INTERCEPT'],
  },
]

interface BusinessNode {
  business_code: string
  target: string
  step_name: string
  technical: string[]
  status: PipelineStepStatus
  summary: string
  current: boolean
  representative?: PipelineStep
}

function mergeStatus(steps: PipelineStep[]): PipelineStepStatus {
  if (!steps.length) return 'pending'
  if (steps.some((step) => step.status === 'failed')) return 'failed'
  if (steps.some((step) => step.status === 'dirty')) return 'dirty'
  if (steps.some((step) => step.status === 'running')) return 'running'
  if (steps.some((step) => step.status === 'manual_edited')) return 'manual_edited'
  if (steps.some((step) => step.status === 'warning')) return 'warning'
  return 'success'
}

function summaryFor(steps: PipelineStep[], status: PipelineStepStatus): string {
  if (!steps.length) return '待执行'
  if (status === 'running') return '执行中…'
  if (status === 'failed') return '失败'
  if (status === 'dirty') return '上游已改，需重跑'
  const ruleIds = new Set<string>()
  const warnings = new Set<string>()
  let fieldCount = 0
  steps.forEach((step) => {
    ;[...(step.rule_hits || []), ...(step.conversions || [])].forEach((item: any) => {
      const id = String(item.rule_id || item.rule_code || '')
      if (id) ruleIds.add(id)
    })
    ;(step.warnings || []).forEach((item) => warnings.add(String(item)))
    fieldCount = Math.max(fieldCount, Object.keys(step.fields || {}).length)
  })
  const parts: string[] = []
  if (ruleIds.size) parts.push(`命中 ${ruleIds.size}`)
  if (fieldCount) parts.push(`字段 ${fieldCount}`)
  if (warnings.size) parts.push(`警示 ${warnings.size}`)
  return parts.join(' · ') || '完成'
}

const nodes = computed<BusinessNode[]>(() => {
  const all = props.steps || []
  return BUSINESS_STEPS.map((def) => {
    const techSteps = all.filter((step) => def.technical.includes(step.step_code))
    const representative = def.target === 'RISK_INTERCEPT'
      ? techSteps.find((step) => step.step_code === 'RISK_INTERCEPT')
      : techSteps[0]
    const status = mergeStatus(techSteps)
    return {
      ...def,
      status,
      representative,
      summary: summaryFor(techSteps, status),
      current: def.technical.includes(props.currentStepCode || ''),
    }
  })
})

function onNodeClick(node: BusinessNode) {
  if (props.disabled) return
  if (node.representative && node.target === node.representative.step_code) {
    emit('select', node.representative)
    return
  }
  emit('select', {
    id: undefined,
    step_code: node.target,
    step_name: node.step_name,
    step_order: node.target === 'RISK_INTERCEPT' ? 50 : ({ MEDICAL_TERM: 10, BASE_CLEANING: 20, NUMBER_NORMALIZE: 30, BUSINESS_SEGMENT: 40 } as any)[node.target],
    status: 'pending',
    input_text: '',
    output_text: '',
    conversions: [],
    rule_hits: [],
    warnings: [],
    state_before: {},
    state_after: {},
    fields: {},
    source_spans: [],
    duration_ms: 0,
    config_hash: '',
  })
}
</script>

<style scoped>
.interactive-steps { padding: 14px 12px; }
.steps-track { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.step-node { position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 4px; border-radius: 8px; cursor: default; transition: background .2s; min-width: 0; }
.step-node.clickable { cursor: pointer; }
.step-node.clickable:hover { background: #f5f5f5; }
.step-node.current { background: #e6f4ff; box-shadow: inset 0 0 0 1px #91caff; }
.step-badge { position: relative; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; font-weight: 600; }
.step-index { position: relative; z-index: 1; }
.step-status-spin { position: absolute; inset: 0; border-radius: 50%; border: 2px solid rgba(22,119,255,.3); border-top-color: #1677ff; animation: step-spin .9s linear infinite; }
.step-status-dot { position: absolute; width: 8px; height: 8px; border-radius: 50%; right: -2px; bottom: -2px; border: 1.5px solid #fff; }
.step-name { font-size: 12.5px; font-weight: 500; text-align: center; line-height: 1.3; }
.step-summary { font-size: 11px; color: #888; text-align: center; line-height: 1.3; min-height: 14px; }
.status-pending .step-badge { background: #bfbfbf; }
.status-running .step-badge { background: #1677ff; }
.status-success .step-badge { background: #52c41a; }
.status-warning .step-badge { background: #fa8c16; }
.status-failed .step-badge { background: #ff4d4f; }
.status-manual_edited .step-badge { background: #722ed1; }
.status-dirty .step-badge { background: #d46b08; }
@keyframes step-spin { to { transform: rotate(360deg); } }
@media (max-width: 900px) { .steps-track { grid-template-columns: repeat(5, minmax(150px, 1fr)); overflow-x: auto; } }
</style>
