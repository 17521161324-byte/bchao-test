<template>
  <a-steps
    v-if="items.length"
    size="small"
    :current="currentIndex"
    :items="items"
    class="pipeline-steps"
  />
  <a-empty v-else description="暂无执行步骤" :image-style="{ height: '40px' }" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineStep, PipelineStepStatus } from '@/types/conversionPipeline'

const props = defineProps<{
  steps: PipelineStep[]
  currentStepOrder?: number
}>()

const emit = defineEmits<{
  (e: 'select', step: PipelineStep): void
}>()

/** 步骤状态 → a-steps 状态（pending → wait / running → process / success → finish / failed → error） */
const statusMap: Record<PipelineStepStatus, 'wait' | 'process' | 'finish' | 'error'> = {
  pending: 'wait',
  running: 'process',
  success: 'finish',
  failed: 'error',
}

const items = computed(() => props.steps.map((step) => ({
  title: `${step.step_order}. ${step.step_name}`,
  description: statusText(step.status),
  status: statusMap[step.status] || 'wait',
  onClick: () => emit('select', step),
})))

const currentIndex = computed(() => {
  if (!props.steps.length) return 0
  const idx = props.steps.findIndex((step) => step.step_order === props.currentStepOrder)
  return idx >= 0 ? idx : props.steps.length - 1
})

function statusText(status: PipelineStepStatus) {
  return ({
    pending: '待执行',
    running: '执行中',
    success: '完成',
    failed: '失败',
  } as Record<PipelineStepStatus, string>)[status] || status
}
</script>

<style scoped>
.pipeline-steps {
  padding: 8px 4px;
}
</style>
