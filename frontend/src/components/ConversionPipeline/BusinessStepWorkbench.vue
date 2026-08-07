<template>
  <div class="business-step-workbench">
    <StepWorkbench
      :step="displayStep"
      :editing="editing"
      :busy="busy"
      @edit="$emit('edit')"
      @cancel-edit="$emit('cancel-edit')"
      @save-edit="$emit('save-edit', $event)"
      @restore-system="$emit('restore-system')"
      @rerun="$emit('rerun')"
      @open-drawer="$emit('open-drawer', $event)"
    />

    <section v-if="isFinalBusinessStep" class="panel aggregate-panel">
      <div class="aggregate-title">
        <strong>字段解析、校验与分流</strong>
        <a-tag :color="aggregateRiskColor">{{ aggregateRiskLabel }}</a-tag>
      </div>
      <BusinessSegmentCards
        :segments="businessSegments"
        :fields="fieldStep?.fields || {}"
        :risks="aggregateRisks"
        :warnings="aggregateWarnings"
      />
    </section>

    <section class="panel diagnostic-panel">
      <RuleExecutionDiagnostics :steps="diagnosticSteps" :rule-version-id="ruleVersionId" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineStep } from '@/types/conversionPipeline'
import StepWorkbench from './StepWorkbench.vue'
import BusinessSegmentCards from './BusinessSegmentCards.vue'
import RuleExecutionDiagnostics from './RuleExecutionDiagnostics.vue'

const props = defineProps<{
  step: PipelineStep
  allSteps: PipelineStep[]
  editing: boolean
  busy?: boolean
  ruleVersionId?: number | null
}>()

defineEmits<{
  (e: 'edit'): void
  (e: 'cancel-edit'): void
  (e: 'save-edit', payload: { text: string; note: string; continueNext: boolean }): void
  (e: 'restore-system'): void
  (e: 'rerun'): void
  (e: 'open-drawer', type: 'rules' | 'fields' | 'warnings'): void
}>()

const isFinalBusinessStep = computed(() => props.step.step_code === 'RISK_INTERCEPT')
const fieldStep = computed(() => (props.allSteps || []).find((item) => item.step_code === 'FIELD_PARSE'))
const runtimeStep = computed(() => (props.allSteps || []).find((item) => item.step_code === 'RUNTIME_RULE'))
const riskStep = computed(() => (props.allSteps || []).find((item) => item.step_code === 'RISK_INTERCEPT'))
const segmentStep = computed(() => (props.allSteps || []).find((item) => item.step_code === 'BUSINESS_SEGMENT'))


const displayStep = computed<PipelineStep>(() => {
  if (!isFinalBusinessStep.value) return props.step
  const technical = [fieldStep.value, runtimeStep.value, riskStep.value].filter(Boolean) as PipelineStep[]
  const field = fieldStep.value
  const risk = riskStep.value || props.step
  return {
    ...risk,
    step_code: 'RISK_INTERCEPT',
    step_name: '字段解析、校验与分流',
    step_order: 50,
    input_text: field?.input_text || risk.input_text || '',
    output_text: risk.output_text || field?.output_text || '',
    effective_output_text: risk.effective_output_text || risk.output_text || field?.effective_output_text || field?.output_text || '',
    conversions: technical.flatMap((item) => item.conversions || []),
    rule_hits: field?.rule_hits || [],
    warnings: Array.from(new Set(technical.flatMap((item) => item.warnings || []))),
    fields: field?.fields || risk.fields || {},
    source_spans: field?.source_spans || [],
    duration_ms: technical.reduce((sum, item) => sum + Number(item.duration_ms || 0), 0),
  }
})

const businessSegments = computed(() => fieldStep.value?.rule_hits?.length ? fieldStep.value.rule_hits : (segmentStep.value?.rule_hits || []))
const aggregateRisks = computed(() => [
  ...(fieldStep.value?.conversions || []),
  ...(runtimeStep.value?.conversions || []),
  ...(riskStep.value?.rule_hits || riskStep.value?.conversions || []),
])
const aggregateWarnings = computed(() => Array.from(new Set([
  ...(fieldStep.value?.warnings || []),
  ...(runtimeStep.value?.warnings || []),
  ...(riskStep.value?.warnings || []),
])))
const diagnosticSteps = computed(() => {
  if (!isFinalBusinessStep.value) return [props.step]
  return [fieldStep.value, runtimeStep.value, riskStep.value].filter(Boolean) as PipelineStep[]
})
const aggregateRiskLabel = computed(() => {
  const risks = aggregateRisks.value
  if (risks.some((item: any) => item.action === 'BLOCK')) return '需回听'
  if (risks.some((item: any) => ['REVIEW', 'CANDIDATE'].includes(item.action))) return '需复核'
  return '通过'
})
const aggregateRiskColor = computed(() => aggregateRiskLabel.value === '需回听' ? 'red' : aggregateRiskLabel.value === '需复核' ? 'orange' : 'green')
</script>

<style scoped>
.business-step-workbench { display: grid; gap: 12px; }
.aggregate-panel, .diagnostic-panel { display: grid; gap: 10px; }
.aggregate-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
</style>
