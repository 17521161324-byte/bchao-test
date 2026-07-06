<template>
  <a-modal
    :open="modal.open"
    title="字段对比"
    :footer="null"
    width="680px"
    :body-style="{ padding: '16px' }"
    @cancel="close"
  >
    <div v-if="modal.task" class="fc-grid">
      <a-card title="真实值（Ground Truth）" size="small" class="fc-card">
        <pre class="fc-pre">{{ truth }}</pre>
      </a-card>
      <a-card
        title="转写/识别值"
        size="small"
        class="fc-card"
        :class="{ 'fc-mismatch': isMatch === false }"
      >
        <pre class="fc-pre" :style="{ color: isMatch === false ? '#ff4d4f' : '' }">{{ identified }}</pre>
        <div v-if="isMatch === false" class="fc-badge">
          <CloseOutlined /> 不匹配
          <span v-if="diffText">（差异: {{ diffText }}）</span>
        </div>
      </a-card>
    </div>
    <a-empty v-else description="无评估数据" />
  </a-modal>
</template>

<script lang="ts">
import { defineComponent, computed } from 'vue'
import { CloseOutlined } from '@ant-design/icons-vue'
import { useFieldCompare } from '@/composables/useFieldCompare'

export default defineComponent({
  name: 'FieldCompareModal',
  props: { modal: { type: Object, required: true } },
  emits: ['close'],
  setup(props, { emit }) {
    const { fieldEval } = useFieldCompare()
    const f = computed(() => fieldEval(props.modal.task, props.modal.field))
    const isMatch = computed(() => f.value?.match ?? null)
    const truth = computed(() => {
      const v = f.value?.truth
      return v === null || v === undefined ? '-' : JSON.stringify(v, null, 2)
    })
    const identified = computed(() => {
      const v = f.value?.identified
      return v === null || v === undefined ? '-' : JSON.stringify(v, null, 2)
    })
    const diffText = computed(() => {
      const d = f.value?.diff
      return d == null ? '' : String(d)
    })
    return {
      isMatch, truth, identified, diffText,
      close: () => emit('close'),
      CloseOutlined,
    }
  },
})
</script>

<style scoped>
.fc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.fc-card { border: 2px solid transparent; }
.fc-mismatch { border-color: #ff4d4f; background: #fff1f0; }
.fc-pre { white-space: pre-wrap; word-break: break-all; font-size: 12px; }
.fc-badge { margin-top: 8px; color: #ff4d4f; font-weight: bold; }
</style>
