<template>
  <div class="step-input-output">
    <div class="io-grid">
      <div class="io-card">
        <div class="io-title">本步骤输入</div>
        <pre class="io-text">{{ step.input_text || '-' }}</pre>
        <div v-if="warnings.length" class="warnings">
          <div class="io-title">警示</div>
          <a-alert
            v-for="(warning, idx) in warnings"
            :key="idx"
            type="warning"
            show-icon
            :message="warning"
            class="warning-item"
          />
        </div>
      </div>

      <div class="io-card">
        <div class="io-title">本步骤输出</div>
        <pre class="io-text">{{ step.output_text || '-' }}</pre>
        <div v-if="errorMessage" class="error-message">{{ errorMessage }}</div>
      </div>
    </div>

    <div class="io-card diff-card">
      <div class="io-title">
        输入 / 输出差异
        <span class="legend">
          <span class="legend-del">删除</span>
          <span class="legend-add">新增</span>
        </span>
      </div>
      <template v-if="diffSegments.length">
        <pre class="diff-text"><span v-for="(seg, idx) in diffSegments" :key="idx" :class="`diff-${seg.type}`">{{ seg.text }}</span></pre>
        <div class="muted">说明：按词级比对（LCS），仅高亮内容差异，非精确逐字 diff。</div>
      </template>
      <div v-else class="muted">-</div>
    </div>

    <div class="io-card">
      <div class="io-title">结构化字段</div>
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

    <div class="io-card">
      <div class="io-title">来源区间（source spans）</div>
      <a-table
        v-if="spanRows.length"
        size="small"
        row-key="spk"
        :columns="spanColumns"
        :data-source="spanRows"
        :pagination="false"
      />
      <span v-else class="muted">无来源区间</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineStep } from '@/types/conversionPipeline'

const props = defineProps<{
  step: PipelineStep
}>()

const warnings = computed(() => props.step.warnings || [])
const errorMessage = computed(() => props.step.error_message || '')

const fieldRows = computed(() =>
  Object.entries(props.step.fields || {}).map(([key, value]) => ({
    key,
    label: fieldLabels[key] || key,
    value: formatValue(value),
  })),
)

const spanRows = computed(() =>
  (props.step.source_spans || []).map((span, idx) => ({
    ...span,
    spk: `sp-${idx}`,
    text_preview: String(span.text ?? span.raw_text ?? span.value ?? '-').slice(0, 80),
  })),
)

const diffSegments = computed(() => simpleDiff(props.step.input_text || '', props.step.output_text || ''))

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

const spanColumns = [
  { title: '字段', dataIndex: 'field_code', key: 'field_code', width: 170 },
  { title: '原文', dataIndex: 'text_preview', key: 'text_preview' },
  { title: '区间', key: 'range', width: 130, customRender: ({ record }: any) => renderRange(record) },
  { title: '说明', dataIndex: 'note', key: 'note', width: 140 },
]

function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item: any) => (typeof item === 'object' ? JSON.stringify(item) : item)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function renderRange(record: any) {
  const start = record.start ?? record.start_offset ?? record.begin
  const end = record.end ?? record.end_offset
  if (start === undefined || end === undefined) return '-'
  return `${start}-${end}`
}

// ========== 简单 diff（诚实实现，不伪造精确 diff） ==========
export interface DiffSegment {
  type: 'same' | 'del' | 'add'
  text: string
}

function tokenize(text: string): string[] {
  return text.match(/\S+|\s+/g) || []
}

/**
 * 按词级（保留空白 token）做 LCS 比对，合并相邻同类段后返回。
 * 纯空白的新增/删除视为噪声丢弃；文本过长时降级为整段并排，不逐词比对。
 */
function simpleDiff(oldText: string, newText: string): DiffSegment[] {
  if (oldText === newText) return [{ type: 'same', text: oldText }]
  const oldTokens = tokenize(oldText)
  const newTokens = tokenize(newText)
  if (!oldTokens.length || !newTokens.length || oldTokens.length > 500 || newTokens.length > 500) {
    return [
      ...(oldText ? [{ type: 'del' as const, text: oldText }] : []),
      ...(newText ? [{ type: 'add' as const, text: newText }] : []),
    ]
  }

  const n = oldTokens.length
  const m = newTokens.length
  // dp[i][j]：oldTokens[0..i) 与 newTokens[0..j) 的 LCS 长度
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] = oldTokens[i - 1] === newTokens[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1])
    }
  }

  const raw: DiffSegment[] = []
  let i = n
  let j = m
  while (i > 0 && j > 0) {
    if (oldTokens[i - 1] === newTokens[j - 1]) {
      raw.push({ type: 'same', text: oldTokens[i - 1] })
      i--
      j--
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      raw.push({ type: 'del', text: oldTokens[i - 1] })
      i--
    } else {
      raw.push({ type: 'add', text: newTokens[j - 1] })
      j--
    }
  }
  while (i > 0) { raw.push({ type: 'del', text: oldTokens[i - 1] }); i-- }
  while (j > 0) { raw.push({ type: 'add', text: newTokens[j - 1] }); j-- }
  raw.reverse()

  // 丢弃纯空白的新增/删除（空白变化视为噪声），再合并相邻同类段
  const merged: DiffSegment[] = []
  for (const seg of raw) {
    if ((seg.type === 'del' || seg.type === 'add') && /^\s*$/.test(seg.text)) continue
    const last = merged[merged.length - 1]
    if (last && last.type === seg.type) last.text += seg.text
    else merged.push({ ...seg })
  }
  return merged
}
</script>

<style scoped>
.step-input-output {
  display: grid;
  gap: 12px;
}
.io-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.io-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px;
  min-width: 0;
}
.io-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 8px;
}
.io-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
}
.legend {
  display: inline-flex;
  gap: 6px;
  font-size: 12px;
  font-weight: 400;
}
.legend-del {
  color: #cf1322;
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 4px;
  padding: 0 6px;
}
.legend-add {
  color: #389e0d;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 4px;
  padding: 0 6px;
}
.diff-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
}
.diff-del {
  color: #cf1322;
  background: #fff1f0;
  text-decoration: line-through;
  border-radius: 3px;
  padding: 0 1px;
}
.diff-add {
  color: #389e0d;
  background: #f6ffed;
  border-radius: 3px;
  padding: 0 1px;
}
.muted { color: #888; font-size: 12px; }
.warning-item { margin-bottom: 6px; }
.error-message {
  color: #cf1322;
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 4px;
  padding: 6px 10px;
  margin-top: 8px;
}
</style>
