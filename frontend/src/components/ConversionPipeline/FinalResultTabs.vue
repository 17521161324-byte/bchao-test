<template>
  <section class="final-result-tabs panel">
    <a-tabs v-if="execution" v-model:activeKey="activeKey" class="final-tabs">
      <!-- 最终文本 -->
      <a-tab-pane key="text" tab="最终文本">
        <div class="text-tab-actions">
          <a-space wrap>
            <a-button size="small" @click="copy(execution.final_text)">复制最终文本</a-button>
            <a-button size="small" @click="exportText">导出最终文本</a-button>
          </a-space>
        </div>
        <div class="final-grid">
          <div class="ft-card">
            <div class="ft-title">原始文本</div>
            <pre class="ft-text">{{ execution.input_text || '-' }}</pre>
          </div>
          <div class="ft-card">
            <div class="ft-title">最终文本</div>
            <pre class="ft-text">{{ execution.final_text || '-' }}</pre>
          </div>
          <div class="ft-card">
            <div class="ft-title">
              差异高亮
              <span class="legend">
                <span class="legend-del">删除</span>
                <span class="legend-add">新增</span>
              </span>
            </div>
            <pre class="ft-text"><span v-for="(seg, idx) in finalDiff" :key="idx" :class="`diff-${seg.type}`">{{ seg.text }}</span></pre>
            <div class="muted">说明：按词级比对（LCS），仅高亮内容差异，非精确逐字 diff。</div>
          </div>
        </div>
      </a-tab-pane>

      <!-- 结构化字段 -->
      <a-tab-pane key="fields" tab="结构化字段">
        <a-table
          v-if="businessFieldRows.length"
          size="small"
          row-key="key"
          :columns="fieldColumns"
          :data-source="businessFieldRows"
          :pagination="false"
          class="fields-table"
        />
        <span v-else class="muted">未解析出业务字段</span>
        <a-collapse v-if="otherFieldRows.length || rawJson" ghost class="raw-json-collapse">
          <a-collapse-panel v-if="otherFieldRows.length" key="other" header="其他字段（{{ otherFieldRows.length }}）">
            <a-table size="small" row-key="key" :columns="fieldColumns" :data-source="otherFieldRows" :pagination="false" />
          </a-collapse-panel>
          <a-collapse-panel v-if="rawJson" key="raw" header="查看原始 JSON">
            <pre class="raw-json">{{ rawJson }}</pre>
          </a-collapse-panel>
        </a-collapse>
      </a-tab-pane>

      <!-- 风险警示 -->
      <a-tab-pane key="risks" tab="风险警示">
        <template v-if="riskGroups.length">
          <div v-for="group in riskGroups" :key="group.key" class="risk-group">
            <div class="risk-group-title">
              <a-tag :color="group.color">{{ group.label }}</a-tag>
              <span class="muted">{{ group.items.length }} 条</span>
            </div>
            <div v-if="group.items.length" class="risk-list">
              <div v-for="(item, idx) in group.items" :key="idx" class="risk-item">
                <a-tag :color="actionColor(item.action)">{{ item.action || '-' }}</a-tag>
                <span v-if="item.rule_id" class="risk-rule">{{ item.rule_id }}</span>
                <span class="risk-message">{{ item.message || JSON.stringify(item) }}</span>
                <span v-if="riskRawText(item)" class="risk-raw">原文：{{ riskRawText(item) }}</span>
                <span v-if="item.suggestion" class="risk-suggestion">建议：{{ item.suggestion }}</span>
              </div>
            </div>
            <span v-else class="muted">无</span>
          </div>
        </template>
        <a-empty v-else description="无风险警示" />
      </a-tab-pane>

      <!-- 执行历史 -->
      <a-tab-pane key="history" tab="执行历史">
        <a-table
          size="small"
          row-key="id"
          :columns="historyColumns"
          :data-source="history"
          :pagination="false"
          :loading="busy"
          :custom-row="historyRow"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'result_level'">
              <a-tag v-if="record.result_level" :color="levelColor(record.result_level)">{{ levelLabel(record.result_level) }}</a-tag>
              <span v-else>-</span>
            </template>
            <template v-else-if="column.key === 'manual'">
              <a-tag v-if="record.manual_edited || record.edited" color="purple">已人工修改</a-tag>
              <span v-else>-</span>
            </template>
            <template v-else-if="column.key === 'ops'">
              <a-space size="small">
                <a-button size="small" type="link" @click="emit('view', record)">查看</a-button>
                <a-button size="small" type="link" @click="emit('compare', record)">对比</a-button>
              </a-space>
            </template>
          </template>
        </a-table>
        <div v-if="!history.length && !busy" class="history-empty muted">暂无历史调试记录</div>
      </a-tab-pane>
    </a-tabs>

    <a-empty v-else description="运行后将在此展示最终结果" :image-style="{ height: '60px' }" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import type {
  PipelineExecution,
  PipelineExecutionSummary,
  PipelineResultLevel,
} from '@/types/conversionPipeline'
import { simpleDiff } from './diff'

const props = defineProps<{
  execution: PipelineExecution | null
  history: PipelineExecutionSummary[]
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: 'view', execution: PipelineExecutionSummary): void
  (e: 'compare', execution: PipelineExecutionSummary): void
}>()

const activeKey = ref('text')

const finalDiff = computed(() => simpleDiff(props.execution?.input_text || '', props.execution?.final_text || ''))

/** 业务字段优先顺序（含各页面已有 label 汇总） */
const FIELD_LABELS: Array<[string, string]> = [
  ['endometrium_thickness', '内膜厚度'],
  ['endometrium_type', '内膜类型'],
  ['right_ovary_size', '右卵巢大小'],
  ['right_ovary_length', '右卵巢长'],
  ['right_ovary_width', '右卵巢宽'],
  ['left_ovary_size', '左卵巢大小'],
  ['left_ovary_length', '左卵巢长'],
  ['left_ovary_width', '左卵巢宽'],
  ['right_follicle_total', '右卵泡总数'],
  ['right_follicles', '右侧卵泡'],
  ['left_follicle_total', '左卵泡总数'],
  ['left_follicles', '左侧卵泡'],
  ['current_side', '当前侧别'],
  ['ultrasound_findings', '超声描述'],
  ['procedure_info', '操作信息'],
  ['followup_orders', '随访医嘱'],
  ['mentioned_count', '提及数量'],
  ['noise_segment', '噪声片段'],
  ['remark', '备注'],
]

const fieldLabelMap = new Map(FIELD_LABELS)
const fieldRows = computed(() => {
  const fields = props.execution?.final_fields || {}
  return Object.entries(fields).map(([key, value]) => ({
    key,
    label: fieldLabelMap.get(key) || key,
    value: formatValue(value),
  }))
})
const businessFieldRows = computed(() => {
  const known = new Set(FIELD_LABELS.map(([key]) => key))
  const sorted = [...fieldRows.value].sort((a, b) => {
    const ia = known.has(a.key) ? FIELD_LABELS.findIndex(([k]) => k === a.key) : 999
    const ib = known.has(b.key) ? FIELD_LABELS.findIndex(([k]) => k === b.key) : 999
    return ia - ib
  })
  return sorted.filter((row) => known.has(row.key))
})
const otherFieldRows = computed(() => fieldRows.value.filter((row) => !businessFieldRows.value.some((item) => item.key === row.key)))
const rawJson = computed(() => {
  const fields = props.execution?.final_fields || {}
  return Object.keys(fields).length ? JSON.stringify(fields, null, 2) : ''
})

interface RiskGroup {
  key: string
  label: string
  color: string
  items: Record<string, any>[]
}
const riskGroups = computed<RiskGroup[]>(() => {
  const items = props.execution?.final_risk_items || []
  const groups: Record<string, RiskGroup> = {
    must_review: { key: 'must_review', label: '必须回听', color: 'red', items: [] },
    need_review: { key: 'need_review', label: '需要人工复核', color: 'orange', items: [] },
    normal: { key: 'normal', label: '普通提示', color: 'default', items: [] },
  }
  items.forEach((item) => {
    if (item.action === 'BLOCK') groups.must_review.items.push(item)
    else if (['REVIEW', 'CANDIDATE'].includes(item.action)) groups.need_review.items.push(item)
    else groups.normal.items.push(item)
  })
  return [groups.must_review, groups.need_review, groups.normal]
})

const fieldColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 180 },
  { title: '值', dataIndex: 'value', key: 'value' },
]

const historyColumns = [
  { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 150, customRender: ({ text }: any) => formatTime(text) },
  { title: '规则版本', dataIndex: 'rule_version_code', key: 'rule_version_code', width: 150 },
  { title: '结果等级', key: 'result_level', width: 120 },
  { title: '人工修改', key: 'manual', width: 100 },
  { title: '操作', key: 'ops', width: 130 },
]

function historyRow(record: PipelineExecutionSummary) {
  return { onClick: () => emit('view', record) }
}

function riskRawText(item: Record<string, any>) {
  const raw = item.raw ?? item.raw_text ?? item.details?.raw ?? item.details?.raw_text
  return raw ? String(raw) : ''
}

function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item: any) => (typeof item === 'object' ? JSON.stringify(item) : item)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function actionColor(action: string) {
  return ({ AUTO: 'green', CANDIDATE: 'blue', REVIEW: 'orange', BLOCK: 'red', WARN: 'gold' } as any)[action] || 'default'
}

function levelColor(level: PipelineResultLevel) {
  return ({ AUTO_ACCEPT: 'green', REVIEW_REQUIRED: 'orange', MANUAL_AUDIO_REVIEW: 'red' } as Record<PipelineResultLevel, string>)[level] || 'default'
}

function levelLabel(level: PipelineResultLevel) {
  return ({ AUTO_ACCEPT: '自动接受', REVIEW_REQUIRED: '需人工复核', MANUAL_AUDIO_REVIEW: '需回听' } as Record<PipelineResultLevel, string>)[level] || level
}

function formatTime(value?: string) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : '-'
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text || '')
    message.success('已复制')
  } catch {
    message.error('复制失败，请手动复制')
  }
}

function exportText() {
  const text = props.execution?.final_text || ''
  const rule = props.execution?.rule_version_code || 'manual'
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `conversion-final-${props.execution?.id || Date.now()}-${rule}.txt`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.final-result-tabs { min-width: 0; }
.final-tabs :deep(.ant-tabs-nav) { margin-bottom: 12px; }
.text-tab-actions { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.final-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.ft-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px;
  min-width: 0;
}
.ft-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.ft-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 260px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  font-size: 13px;
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
}
.legend { display: inline-flex; gap: 6px; font-size: 12px; font-weight: 400; }
.legend-del { color: #cf1322; background: #fff1f0; border: 1px solid #ffa39e; border-radius: 4px; padding: 0 6px; }
.legend-add { color: #389e0d; background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 4px; padding: 0 6px; }
.diff-del { color: #cf1322; background: #fff1f0; text-decoration: line-through; border-radius: 3px; padding: 0 1px; }
.diff-add { color: #389e0d; background: #f6ffed; border-radius: 3px; padding: 0 1px; }
.fields-table { margin-bottom: 4px; }
.raw-json-collapse :deep(.ant-collapse-header) {
  padding: 6px 0 !important;
  font-size: 13px;
}
.raw-json {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 300px;
  overflow: auto;
  font-family: inherit;
  font-size: 12px;
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
}
.risk-group { margin-bottom: 14px; }
.risk-group-title { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.risk-list { display: grid; gap: 6px; }
.risk-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  flex-wrap: wrap;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  line-height: 1.6;
}
.risk-rule { font-weight: 600; color: #1677ff; }
.risk-message { flex: 1; min-width: 200px; }
.risk-raw { color: #888; background: #fafafa; border-radius: 4px; padding: 0 6px; }
.risk-suggestion { color: #666; }
.history-empty { padding: 16px 0; text-align: center; }
.muted { color: #888; font-size: 12px; }
@media (max-width: 1100px) {
  .final-grid { grid-template-columns: 1fr; }
}
</style>
