<template>
  <div class="debug-step-cards">
    <div
      v-for="(card, index) in cards"
      :key="card.code"
      class="step-card"
      :class="{ current: card.code === currentCode, clickable: true }"
      @click="$emit('select', card.code)"
    >
      <span class="step-badge">{{ String(index + 1).padStart(2, '0') }}</span>
      <div class="step-name">{{ card.name }}</div>
      <div class="step-summary">{{ card.summary }}</div>
      <div class="step-status" :class="card.candidateCount > 0 ? 'has-candidate' : 'done'">
        {{ card.statusText }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineStep } from '@/types/conversionPipeline'
import {
  BUSINESS_STEPS,
  candidateCount,
  collectObserved,
  stepExecuted,
  techStepsOf,
} from './debug'

const props = defineProps<{
  steps: PipelineStep[]
  currentCode: string
}>()

defineEmits<{
  (e: 'select', code: string): void
}>()

interface StepCard {
  code: string
  name: string
  summary: string
  statusText: string
  candidateCount: number
}

const cards = computed<StepCard[]>(() =>
  BUSINESS_STEPS.map((def) => {
    const technical = techStepsOf(props.steps || [], def.code)
    const executed = stepExecuted(technical)
    const observed = collectObserved(technical)
    const warnings = Array.from(new Set((technical || []).flatMap((step) => step.warnings || [])))
    const candidates = candidateCount(observed, warnings)
    const ruleCount = new Set(observed.map((item) => item.rule_id)).size
    return {
      code: def.code,
      name: def.name,
      summary: executed ? `规则 ${ruleCount} 条` : '尚未执行',
      statusText: executed
        ? (candidates > 0 ? `⚠️ ${candidates} 项候选` : '✅ 完成')
        : '未执行',
      candidateCount: candidates,
    }
  })
)
</script>

<style scoped>
.debug-step-cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(145px, 1fr));
  gap: 10px;
}
.step-card {
  position: relative;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  padding: 12px 12px 10px;
  cursor: pointer;
  display: grid;
  gap: 4px;
  transition: border-color 0.15s, box-shadow 0.15s;
  min-width: 0;
}
.step-card:hover { border-color: #a0cfff; }
.step-card.current {
  border-color: #409eff;
  box-shadow: 0 0 0 1px #409eff inset;
  background: #f5faff;
}
.step-badge {
  position: absolute;
  top: 8px;
  right: 10px;
  font-size: 12px;
  font-weight: 700;
  color: #c0c6d0;
}
.step-card.current .step-badge { color: #409eff; }
.step-name {
  font-size: 13px;
  font-weight: 600;
  color: #1f2329;
  line-height: 1.4;
  padding-right: 22px;
}
.step-summary { font-size: 12px; color: #7a8494; }
.step-status {
  align-self: flex-start;
  font-size: 12px;
  border-radius: 4px;
  padding: 1px 8px;
  line-height: 20px;
}
.step-status.done {
  background: #f0f9eb;
  color: #529b2e;
}
.step-status.has-candidate {
  background: #fdf6ec;
  color: #b88230;
}
</style>
