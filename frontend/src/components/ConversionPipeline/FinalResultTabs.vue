<template>
  <section class="final-result-tabs panel">
    <a-tabs v-if="execution" v-model:activeKey="activeKey" class="final-tabs">
      <a-tab-pane key="compare" tab="数据对比">
        <div class="compare-head">
          <a-space wrap>
            <a-tag v-if="execution.source_record_id">病历号 {{ execution.source_record_id }}</a-tag>
            <a-tag v-if="execution.source_date">{{ execution.source_date }}</a-tag>
            <a-tag v-if="execution.source_config_hash">ASR指纹 {{ shortHash(execution.source_config_hash) }}</a-tag>
          </a-space>
          <span class="muted">当前字段来自本次规则流水线；真实结果来自检查记录真实B超结果，不做模拟回填。</span>
        </div>
        <a-table
          v-if="compareRows.length"
          size="small"
          row-key="key"
          :columns="compareColumns"
          :data-source="compareRows"
          :pagination="false"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-tag :color="record.status === '一致' ? 'green' : record.status === '无真实值' ? 'default' : 'orange'">
                {{ record.status }}
              </a-tag>
            </template>
          </template>
        </a-table>
        <a-empty v-else description="当前检查记录未关联真实B超结果" :image-style="{ height: '56px' }" />
      </a-tab-pane>

      <a-tab-pane key="reference" tab="标准ASR文本">
        <div class="reference-source-note">
          <span class="muted">左侧为当前规则最终转化ASR；右侧只读取人工修正的 AsrReferenceTranscript.reference_text。</span>
        </div>
        <a-alert
          v-if="!execution.reference_text"
          type="warning"
          show-icon
          message="未加载人工修正标准ASR"
          description="不会使用当前转化文本代替标准文本；请先在ASR优化/标准ASR维护中保存人工修正稿。"
          class="reference-alert"
        />
        <template v-else>
          <div class="reference-meta">
            <a-space wrap>
              <a-tag :color="referenceMatchColor">{{ referenceMatchLabel }}</a-tag>
              <span v-if="execution.reference_base_asr_result_id">人工底稿ASR结果ID：{{ execution.reference_base_asr_result_id }}</span>
              <code v-if="execution.reference_base_config_hash">底稿指纹：{{ shortHash(execution.reference_base_config_hash) }}</code>
            </a-space>
          </div>
          <div class="reference-grid">
            <div class="ref-card">
              <div class="ref-title">
                当前转化ASR文本
                <a-button size="small" type="link" @click="copy(execution.final_text)">复制</a-button>
              </div>
              <pre class="ref-text"><template v-for="(seg, idx) in referenceDiff" :key="`l-${idx}`"><span v-if="seg.type !== 'add'" :class="seg.type === 'del' ? 'diff-bad' : ''">{{ seg.text }}</span></template></pre>
            </div>
            <div class="ref-card">
              <div class="ref-title">
                人工修正标准ASR
                <a-button size="small" type="link" @click="copy(execution.reference_text || '')">复制</a-button>
              </div>
              <pre class="ref-text"><template v-for="(seg, idx) in referenceDiff" :key="`r-${idx}`"><span v-if="seg.type !== 'del'" :class="seg.type === 'add' ? 'diff-bad' : ''">{{ seg.text }}</span></template></pre>
            </div>
          </div>
          <div class="muted reference-tip">红色表示两侧不一致内容。匹配关系会区分精确底稿、同指纹和仅同检查记录。</div>
        </template>
      </a-tab-pane>
    </a-tabs>
    <a-empty v-else description="运行后将在此展示最终结果" :image-style="{ height: '60px' }" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { PipelineExecution } from '@/types/conversionPipeline'
import { simpleDiff } from './diff'

const props = defineProps<{
  execution: PipelineExecution | null
}>()

const activeKey = ref('compare')

const FIELD_LABELS: Array<[string, string]> = [
  ['endometrium_thickness', '内膜厚度'],
  ['endometrium_type', '内膜类型'],
  ['right_ovary_size', '右卵巢大小'],
  ['right_follicles', '右侧卵泡'],
  ['left_ovary_size', '左卵巢大小'],
  ['left_follicles', '左侧卵泡'],
  ['remark', '备注'],
]

const compareRows = computed(() => {
  const current = props.execution?.final_fields || {}
  const truth = props.execution?.truth_fields || {}
  if (!Object.keys(truth).length) return []
  return FIELD_LABELS.map(([key, label]) => {
    const currentValue = normalizeFieldValue(key, current[key])
    const truthValue = normalizeFieldValue(key, truth[key])
    let status = '不一致'
    if (truthValue === '-') status = '无真实值'
    else if (currentValue === truthValue) status = '一致'
    return { key, label, current: currentValue, truth: truthValue, status }
  })
})

const compareColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 160 },
  { title: '当前规则结果', dataIndex: 'current', key: 'current' },
  { title: '真实结果', dataIndex: 'truth', key: 'truth' },
  { title: '结果', key: 'status', width: 100 },
]

const referenceDiff = computed(() => simpleDiff(
  props.execution?.final_text || '',
  props.execution?.reference_text || '',
))

const referenceMatchLabel = computed(() => ({
  exact_base: '人工稿与当前ASR底稿完全匹配',
  config_match: '人工稿与当前ASR指纹匹配',
  same_exam: '同一检查记录，但人工稿底稿与当前ASR不同',
} as Record<string, string>)[props.execution?.reference_match_type || ''] || '人工标准ASR')

const referenceMatchColor = computed(() => ({
  exact_base: 'green',
  config_match: 'blue',
  same_exam: 'orange',
} as Record<string, string>)[props.execution?.reference_match_type || ''] || 'default')

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

function shortHash(value: string | null | undefined) {
  if (!value) return '-'
  return value.length > 18 ? `${value.slice(0, 16)}…` : value
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text || '')
    message.success('已复制')
  } catch {
    message.error('复制失败，请手动复制')
  }
}
</script>

<style scoped>
.final-result-tabs { min-width: 0; }
.final-tabs :deep(.ant-tabs-nav) { margin-bottom: 12px; }
.compare-head { display: grid; gap: 6px; margin-bottom: 10px; }
.reference-source-note { margin-bottom: 8px; }
.reference-alert { margin-bottom: 10px; }
.reference-meta { margin-bottom: 10px; }
.reference-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.ref-card { border: 1px solid #e8e8e8; border-radius: 8px; padding: 10px; min-width: 0; }
.ref-title { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-weight: 600; margin-bottom: 8px; }
.ref-text { white-space: pre-wrap; word-break: break-word; margin: 0; min-height: 150px; max-height: 320px; overflow: auto; line-height: 1.7; font-family: inherit; background: #fafafa; border-radius: 6px; padding: 10px; }
.diff-bad { color: #cf1322; background: #fff1f0; border-radius: 3px; padding: 0 1px; }
.reference-tip { margin-top: 8px; }
.muted { color: #8c8c8c; font-size: 12px; }
@media (max-width: 1000px) { .reference-grid { grid-template-columns: 1fr; } }
</style>
