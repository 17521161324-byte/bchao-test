<template>
  <div class="execution-summary">
    <div class="summary-head">
      <div class="summary-title">
        执行摘要
        <a-tag v-if="execution.result_level" :color="levelColor(execution.result_level)">{{ levelText(execution.result_level) }}</a-tag>
        <a-tag :color="statusColor(execution.status)">{{ execution.status }}</a-tag>
      </div>
      <a-space wrap>
        <a-tag>{{ (execution.steps || []).length }} 个步骤</a-tag>
        <a-tag>{{ Object.keys(execution.final_fields || {}).length }} 个字段</a-tag>
        <a-tag :color="(execution.final_risk_items || []).length ? 'orange' : 'default'">{{ (execution.final_risk_items || []).length }} 条风险</a-tag>
      </a-space>
    </div>

    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-card-title">最终文本</div>
        <pre class="final-text">{{ execution.final_text || '-' }}</pre>
      </div>

      <div class="summary-card">
        <div class="summary-card-title">最终字段</div>
        <a-table
          v-if="fieldRows.length"
          size="small"
          row-key="key"
          :columns="fieldColumns"
          :data-source="fieldRows"
          :pagination="false"
        />
        <span v-else class="muted">未解析出字段</span>
      </div>

      <div class="summary-card">
        <div class="summary-card-title">风险项（{{ (execution.final_risk_items || []).length }}）</div>
        <div v-if="riskRows.length" class="risk-list">
          <div v-for="(item, idx) in riskRows" :key="idx" class="risk-item">
            <a-tag color="orange">{{ item.rule_id || '-' }}</a-tag>
            <span class="risk-message">{{ item.message || JSON.stringify(item) }}</span>
          </div>
        </div>
        <span v-else class="muted">无风险项</span>
      </div>
    </div>

    <a-alert
      v-if="(execution.final_warnings || []).length"
      type="warning"
      show-icon
      class="warnings-alert"
      :message="`规则警示文本 ${execution.final_warnings.length} 条`"
      :description="execution.final_warnings.join('；')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineExecution, PipelineResultLevel } from '@/types/conversionPipeline'

const props = defineProps<{
  execution: PipelineExecution
}>()

const fieldRows = computed(() =>
  Object.entries(props.execution.final_fields || {}).map(([key, value]) => ({
    key,
    label: fieldLabels[key] || key,
    value: formatValue(value),
  })),
)

const riskRows = computed(() => props.execution.final_risk_items || [])

const fieldLabels: Record<string, string> = {
  endometrium_thickness: '内膜厚度',
  endometrium_type: '内膜类型',
  right_ovary_size: '右卵巢大小',
  left_ovary_size: '左卵巢大小',
  right_follicles: '右卵泡明细',
  left_follicles: '左卵泡明细',
  current_side: '当前侧别',
  ultrasound_findings: '超声发现',
  procedure_info: '操作信息',
  followup_orders: '随访医嘱',
  mentioned_count: '提及数量',
  noise_segment: '噪声片段',
  remark: '备注',
}

const fieldColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 180 },
  { title: '值', dataIndex: 'value', key: 'value' },
]

function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item: any) => (typeof item === 'object' ? JSON.stringify(item) : item)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function levelColor(level: PipelineResultLevel) {
  return ({
    AUTO_ACCEPT: 'green',
    REVIEW_REQUIRED: 'orange',
    MANUAL_AUDIO_REVIEW: 'red',
  } as Record<PipelineResultLevel, string>)[level] || 'default'
}

function levelText(level: PipelineResultLevel) {
  return ({
    AUTO_ACCEPT: '自动接受',
    REVIEW_REQUIRED: '需人工复核',
    MANUAL_AUDIO_REVIEW: '需回听音频',
  } as Record<PipelineResultLevel, string>)[level] || level
}

function statusColor(status: string) {
  return ({ success: 'green', failed: 'red', running: 'processing', pending: 'default' } as any)[status] || 'default'
}
</script>

<style scoped>
.execution-summary {
  display: grid;
  gap: 12px;
}
.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.summary-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.summary-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px;
  min-width: 0;
}
.summary-card-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.final-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 240px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
}
.risk-list {
  display: grid;
  gap: 6px;
  max-height: 240px;
  overflow: auto;
}
.risk-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.risk-message {
  font-size: 13px;
  line-height: 1.6;
}
.warnings-alert { margin-top: 4px; }
.muted { color: #888; font-size: 12px; }
@media (max-width: 1200px) {
  .summary-grid { grid-template-columns: 1fr; }
}
</style>
