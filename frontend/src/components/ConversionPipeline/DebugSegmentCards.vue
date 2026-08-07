<template>
  <div class="debug-segment-cards">
    <div v-for="card in cards" :key="card.key" class="seg-card" :class="`side-${card.sideKey}`">
      <div class="seg-card-head">
        <strong>{{ card.label }}</strong>
        <a-tag :color="card.review ? 'orange' : 'green'">{{ card.review ? '需复核' : '已定位' }}</a-tag>
      </div>

      <div v-for="(item, idx) in card.items" :key="idx" class="seg-item" :class="{ 'review-item': item.review }">
        <div class="seg-row">
          <span class="seg-k">原始锚点</span>
          <span class="seg-v">{{ item.text || '-' }}</span>
        </div>
        <div v-if="item.normalized !== item.text && item.normalized !== ''" class="seg-row">
          <span class="seg-k">标准化锚点</span>
          <span class="seg-v standard">{{ item.normalized }}</span>
        </div>
        <div v-if="item.note" class="seg-row">
          <span class="seg-k">判定依据</span>
          <span class="seg-v note">{{ item.note }}</span>
        </div>
        <div v-if="item.evidence" class="seg-row">
          <span class="seg-k">源片段</span>
          <span class="seg-v evidence">{{ item.evidence }}</span>
        </div>
        <div v-if="item.rules.length" class="seg-chips">
          <a-tag v-for="chip in item.rules" :key="chip" color="geekblue" class="seg-chip">{{ chip }}</a-tag>
        </div>
        <div v-if="item.review" class="seg-review-note">
          推断说明：该片段未直接修改文本，需人工确认后采纳。
        </div>
      </div>

      <!-- 第5步：字段解析结果表 -->
      <div v-if="showFields && card.fieldRows.length" class="seg-field-table">
        <div class="seg-field-head">字段解析</div>
        <div
          v-for="row in card.fieldRows"
          :key="row.key"
          class="seg-field-row"
          :class="row.status === 'BLOCK' ? 'row-block' : row.status === 'REVIEW' ? 'row-review' : 'row-ok'"
        >
          <span class="ff-label">{{ row.label }}</span>
          <span class="ff-value" :title="row.value">{{ row.value }}</span>
          <span class="ff-status" :class="row.statusClass">{{ row.statusText }}</span>
          <span class="ff-note" :title="row.note">{{ row.note || '-' }}</span>
        </div>
      </div>
    </div>

    <a-empty
      v-if="!cards.length"
      description="本步骤未定位到业务片段"
      :image-style="{ height: '48px' }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  segments: Record<string, any>[]
  fields?: Record<string, any>
  riskItems?: Record<string, any>[]
  showFields?: boolean
}>()

const FIELD_LABELS: Record<string, string> = {
  endometrium_thickness: '内膜厚度',
  endometrium_type: '内膜类型',
  right_ovary_size: '右卵巢大小',
  right_ovary_length: '右卵巢长',
  right_ovary_width: '右卵巢宽',
  right_follicles: '右侧卵泡',
  left_ovary_size: '左卵巢大小',
  left_ovary_length: '左卵巢长',
  left_ovary_width: '左卵巢宽',
  left_follicles: '左侧卵泡',
  remark: '备注',
  ultrasound_findings: '超声描述',
  procedure_info: '操作信息',
  followup_orders: '随访医嘱',
  mentioned_count: '提及数量',
  noise_segment: '噪声片段',
  current_side: '当前侧别',
  side_switch: '换边定位',
  inferred_right_segment: '右卵巢段(反推)',
  inferred_left_segment: '左卵巢段(反推)',
  ovary_size_candidate: '卵巢大小候选',
}

interface CardItem {
  text: string
  normalized: string
  note: string
  evidence: string
  rules: string[]
  review: boolean
}

interface FieldRow {
  key: string
  label: string
  value: string
  status: string
  statusText: string
  statusClass: string
  note: string
}

interface SegmentCard {
  key: string
  sideKey: string
  label: string
  items: CardItem[]
  fieldRows: FieldRow[]
  review: boolean
}

const riskByField = computed(() => {
  const map = new Map<string, Record<string, any>>()
  ;(props.riskItems || []).forEach((item: any) => {
    const field = String(item.field_code || item.field || '')
    if (!field) return
    const prev = map.get(field)
    const precedence: Record<string, number> = { BLOCK: 3, REVIEW: 2, CANDIDATE: 1, AUTO: 0 }
    if (!prev || (precedence[item.action] || 0) > (precedence[prev.action] || 0)) {
      map.set(field, item)
    }
  })
  return map
})

function groupKeyFor(field: string, side: string): string {
  if (field.startsWith('endometrium') || field === 'side_switch' || field === 'inferred_endometrium') return 'endometrium'
  if (field.startsWith('right_') || field === 'inferred_right_segment' || side === 'RIGHT') return 'right'
  if (field.startsWith('left_') || field === 'inferred_left_segment' || side === 'LEFT') return 'left'
  return 'other'
}

const cards = computed<SegmentCard[]>(() => {
  const groups: Record<string, SegmentCard> = {
    endometrium: { key: 'endometrium', sideKey: 'endometrium', label: '内膜', items: [], fieldRows: [], review: false },
    right: { key: 'right', sideKey: 'right', label: '右卵巢', items: [], fieldRows: [], review: false },
    left: { key: 'left', sideKey: 'left', label: '左卵巢', items: [], fieldRows: [], review: false },
    other: { key: 'other', sideKey: 'other', label: '其他', items: [], fieldRows: [], review: false },
  }

  ;(props.segments || []).forEach((item: any) => {
    const field = String(item.field_code || '')
    const key = groupKeyFor(field, String(item.side || ''))
    const action = String(item.action || '').toUpperCase()
    const review = ['REVIEW', 'BLOCK', 'CANDIDATE'].includes(action) || /REVIEW|推断/.test(String(item.note || ''))
    groups[key].items.push({
      text: String(item.text || '-'),
      normalized: item.normalized === null || item.normalized === undefined ? '' : String(item.normalized),
      note: String(item.note || ''),
      evidence: String(item.evidence || ''),
      rules: [String(item.rule_id || '')].filter(Boolean),
      review,
    })
    if (review) groups[key].review = true
  })

  const fields = props.fields || {}
  const orderedFields: Array<[string, any]> = Object.entries(fields)
    .sort(([a], [b]) => FIELD_ORDER.indexOf(a) - FIELD_ORDER.indexOf(b))
  orderedFields.forEach(([fieldKey, value]) => {
    const key = groupKeyFor(fieldKey, '')
    const risk = riskByField.value.get(fieldKey)
    const status = risk?.action ? String(risk.action).toUpperCase() : 'OK'
    groups[key].fieldRows.push({
      key: fieldKey,
      label: FIELD_LABELS[fieldKey] || fieldKey,
      value: format(value),
      status,
      statusText: status === 'BLOCK' ? 'BLOCK' : status === 'REVIEW' ? 'REVIEW' : status === 'CANDIDATE' ? '候选' : 'OK',
      statusClass: status === 'BLOCK' ? 'st-block' : status === 'REVIEW' ? 'st-review' : status === 'CANDIDATE' ? 'st-candidate' : 'st-ok',
      note: risk?.message || String(risk?.notes || risk?.rule_id || ''),
    })
  })

  return Object.values(groups).filter((group) => group.items.length || group.fieldRows.length)
})

const FIELD_ORDER = [
  'endometrium_thickness',
  'endometrium_type',
  'right_ovary_size',
  'right_ovary_length',
  'right_ovary_width',
  'right_follicles',
  'left_ovary_size',
  'left_ovary_length',
  'left_ovary_width',
  'left_follicles',
  'current_side',
  'remark',
  'procedure_info',
  'followup_orders',
  'mentioned_count',
  'noise_segment',
]

function format(value: any): string {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item) => typeof item === 'object' ? JSON.stringify(item) : String(item)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<style scoped>
.debug-segment-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.seg-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
  min-width: 0;
  border-left-width: 4px;
}
.seg-card.side-endometrium { border-left-color: #8b5cf6; }
.seg-card.side-right { border-left-color: #409eff; }
.seg-card.side-left { border-left-color: #67c23a; }
.seg-card.side-other { border-left-color: #909399; }
.seg-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: #fafbfc;
  border-bottom: 1px solid #f0f2f5;
}
.seg-card-head strong { font-size: 13px; color: #1f2329; }
.seg-item {
  padding: 8px 10px;
  border-bottom: 1px dashed #f0f2f5;
  display: grid;
  gap: 4px;
}
.seg-item.review-item { background: #fdf6ec; }
.seg-row { display: flex; gap: 6px; align-items: baseline; }
.seg-k {
  flex: none;
  font-size: 11px;
  color: #a0a8b4;
  width: 56px;
}
.seg-v { font-size: 12px; color: #3d4757; word-break: break-word; }
.seg-v.standard { color: #409eff; }
.seg-v.note { color: #7a8494; }
.seg-v.evidence {
  color: #7a8494;
  font-style: italic;
}
.seg-chips { display: flex; gap: 4px; flex-wrap: wrap; }
.seg-chip { margin-inline-end: 0; font-size: 11px; }
.seg-review-note {
  font-size: 11px;
  color: #b88230;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 4px 8px;
  line-height: 1.5;
}
.seg-field-table { border-top: 1px solid #f0f2f5; }
.seg-field-head {
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #5c6b7a;
  background: #fafbfc;
}
.seg-field-row {
  display: grid;
  grid-template-columns: minmax(64px, auto) minmax(0, 1fr) 52px minmax(0, 1fr);
  gap: 6px;
  align-items: center;
  padding: 5px 10px;
  font-size: 12px;
  border-bottom: 1px solid #f7f8fa;
}
.seg-field-row.row-review { background: #fdf6ec; }
.seg-field-row.row-block { background: #fef0f0; }
.ff-label { color: #5c6b7a; white-space: nowrap; }
.ff-value { color: #1f2329; word-break: break-word; }
.ff-status {
  white-space: nowrap;
  font-weight: 600;
  border-radius: 3px;
  padding: 0 5px;
  line-height: 18px;
  text-align: center;
}
.ff-status.st-ok { background: #f0f9eb; color: #529b2e; }
.ff-status.st-review { background: #fdf6ec; color: #b88230; }
.ff-status.st-candidate { background: #e8f4fd; color: #409eff; }
.ff-status.st-block { background: #fef0f0; color: #d54941; }
.ff-note { color: #7a8494; word-break: break-word; }

@media (max-width: 1400px) {
  .debug-segment-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
