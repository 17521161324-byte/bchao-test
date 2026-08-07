<template>
  <section class="debug-compare-tabs panel">
    <a-tabs v-model:activeKey="activeKey" class="compare-tabs">
      <!-- 数据对比 -->
      <a-tab-pane key="compare" tab="数据对比">
        <a-alert
          v-if="!hasTruth"
          type="info"
          show-icon
          class="truth-callout"
          message="当前记录没有关联真实结果"
          description="未找到该检查记录的真实 B 超结果（BUltraResult），数据对比暂不完整。"
        />
        <a-table
          size="small"
          row-key="key"
          :columns="compareColumns"
          :data-source="compareRows"
          :pagination="false"
          class="compare-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-tag :color="record.statusColor">{{ record.statusText }}</a-tag>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 标准ASR文本 -->
      <a-tab-pane key="reference" tab="标准ASR文本">
        <a-alert
          v-if="!referenceText"
          type="warning"
          show-icon
          class="ref-callout"
          message="当前记录尚未加载人工修正标准ASR"
          description="未找到 AsrReferenceTranscript.reference_text；请先在 ASR 优化 / 标准ASR维护中保存人工修正稿。"
        />
        <template v-else>
          <div class="ref-grid">
            <div class="ref-card">
              <div class="ref-title">
                当前转化ASR文本
                <a-tag :color="execution ? 'green' : 'default'">{{ execution ? '规则输出' : '原始ASR' }}</a-tag>
              </div>
              <pre class="ref-text"><template v-for="(seg, idx) in referenceDiff" :key="`l-${idx}`"><span v-if="seg.type !== 'add'" :class="seg.type === 'del' ? 'diff-bad' : ''">{{ seg.text }}</span></template></pre>
            </div>
            <div class="ref-card">
              <div class="ref-title">
                人工修正标准ASR
                <a-tag color="blue">reference_text</a-tag>
              </div>
              <pre class="ref-text"><template v-for="(seg, idx) in referenceDiff" :key="`r-${idx}`"><span v-if="seg.type !== 'del'" :class="seg.type === 'add' ? 'diff-bad' : ''">{{ seg.text }}</span></template></pre>
            </div>
          </div>
          <div class="muted ref-tip">红色为两侧不一致内容（字符级 LCS 对齐）。未执行规则时左侧展示原始 ASR，便于对照人工稿。</div>
        </template>
      </a-tab-pane>
    </a-tabs>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PipelineExecution } from '@/types/conversionPipeline'
import { simpleDiffChars } from './diff'

const props = defineProps<{
  record: Record<string, any> | null
  execution: PipelineExecution | null
  truth: Record<string, any> | null
  referenceText: string | null
}>()

const activeKey = ref('compare')

const FIELD_ROWS: Array<{ key: string; label: string }> = [
  { key: 'endometrium_thickness', label: '内膜厚度' },
  { key: 'endometrium_type', label: '内膜类型' },
  { key: 'right_ovary_size', label: '右卵巢大小' },
  { key: 'right_follicles', label: '右卵泡明细' },
  { key: 'left_ovary_size', label: '左卵巢大小' },
  { key: 'left_follicles', label: '左卵泡明细' },
  { key: 'remark', label: '备注' },
]

const truthData = computed(() => {
  if (props.execution?.truth_fields && Object.keys(props.execution.truth_fields).length) {
    return props.execution.truth_fields
  }
  return props.truth || {}
})

const hasTruth = computed(() => Object.keys(truthData.value).some((key) => normalizeFieldValue(key, truthData.value[key]) !== '-'))

const candidateFields = computed(() => {
  const set = new Set<string>()
  ;(props.execution?.final_risk_items || []).forEach((item: any) => {
    const action = String(item.action || '').toUpperCase()
    if (['CANDIDATE', 'REVIEW', 'BLOCK'].includes(action) && item.field_code) {
      set.add(String(item.field_code))
    }
  })
  return set
})

const compareRows = computed(() => {
  const current = props.execution?.final_fields || {}
  return FIELD_ROWS.map(({ key, label }) => {
    const currentValue = normalizeFieldValue(key, current[key])
    const truthValue = normalizeFieldValue(key, truthData.value[key])
    let status: 'same' | 'candidate' | 'none' | 'diff'
    let statusText = '差异'
    let statusColor = 'red'
    let note = ''
    if (truthValue === '-') {
      status = 'none'
      statusText = '未关联'
      statusColor = 'default'
      note = '无真实结果可对比'
    } else if (currentValue === truthValue) {
      status = 'same'
      statusText = '一致'
      statusColor = 'green'
      note = '两值一致'
    } else if (candidateFields.value.has(key)) {
      status = 'candidate'
      statusText = '候选一致'
      statusColor = 'orange'
      note = '当前为候选值，与真实结果一致，建议确认后采纳'
    } else {
      status = 'diff'
      statusText = '差异'
      statusColor = 'red'
      note = `规则输出「${currentValue}」，真实「${truthValue}」`
    }
    return { key, label, current: currentValue, truth: truthValue, status, statusText, statusColor, note }
  })
})

const compareColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 130 },
  { title: '字段解析结果', dataIndex: 'current', key: 'current' },
  { title: '真实结果', dataIndex: 'truth', key: 'truth' },
  { title: '对比状态', key: 'status', width: 100 },
  { title: '差异说明', dataIndex: 'note', key: 'note' },
]

const referenceDiff = computed(() => simpleDiffChars(
  props.execution?.final_text || props.record?.full_transcript || '',
  props.referenceText || '',
))

function normalizeFieldValue(key: string, value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (key === 'right_follicles' || key === 'left_follicles') {
    const numbers: number[] = []
    const items = Array.isArray(value) ? value : [value]
    items.forEach((item: any) => {
      if (typeof item === 'object' && item !== null && 'size' in item) {
        const size = Number(item.size)
        const count = Math.max(1, Number(item.count || 1))
        if (Number.isFinite(size)) for (let i = 0; i < count; i += 1) numbers.push(size)
      } else {
        const number = Number(item)
        if (Number.isFinite(number)) numbers.push(number)
      }
    })
    return numbers.sort((a, b) => b - a).map((number) => number.toFixed(1)).join('、') || '-'
  }
  if (Array.isArray(value)) return value.map((item: any) => typeof item === 'object' ? JSON.stringify(item) : String(item)).join('、') || '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<style scoped>
.debug-compare-tabs { min-width: 0; }
.compare-tabs :deep(.ant-tabs-nav) { margin-bottom: 12px; }
.truth-callout, .ref-callout { margin-bottom: 10px; }
.compare-table { width: 100%; }
.ref-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.ref-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px;
  min-width: 0;
  background: #fbfcfe;
}
.ref-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 13px;
  color: #3d4757;
  margin-bottom: 8px;
}
.ref-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  min-height: 130px;
  max-height: 300px;
  overflow: auto;
  line-height: 1.7;
  font-family: inherit;
  font-size: 13px;
  background: #fff;
  border: 1px solid #eef2f6;
  border-radius: 6px;
  padding: 8px;
}
.diff-bad {
  color: #d54941;
  background: #fef0f0;
  border-radius: 3px;
  padding: 0 1px;
}
.ref-tip { margin-top: 8px; }
.muted { color: #a0a8b4; font-size: 12px; }
@media (max-width: 1000px) {
  .ref-grid { grid-template-columns: 1fr; }
}
</style>
