<template>
  <div v-if="cards.length" class="segment-wrap">
    <div class="segment-title">业务片段 / 字段解析校验</div>
    <div class="segment-grid">
      <div v-for="card in cards" :key="card.key" class="segment-card">
        <div class="card-head">
          <strong>{{ card.label }}</strong>
          <a-tag :color="card.review ? 'orange' : 'green'">{{ card.review ? '需复核' : '已定位' }}</a-tag>
        </div>
        <div v-for="(item, idx) in card.items" :key="idx" class="segment-row">
          <div class="segment-meta">
            <a-tag v-if="item.field_code">{{ fieldLabel(item.field_code) }}</a-tag>
            <a-tag v-if="item.side" :color="item.side === 'RIGHT' ? 'blue' : item.side === 'LEFT' ? 'purple' : 'default'">{{ sideLabel(item.side) }}</a-tag>
          </div>
          <div class="raw">{{ item.text || '-' }}</div>
          <div v-if="item.normalized !== undefined && String(item.normalized) !== String(item.text)" class="normalized">
            标准化：{{ format(item.normalized) }}
          </div>
          <div v-if="item.note" class="note">依据：{{ item.note }}</div>
        </div>
        <div v-if="card.fields.length" class="field-box">
          <div v-for="row in card.fields" :key="row.key" class="field-row">
            <span>{{ row.label }}</span><strong>{{ row.value }}</strong>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  segments: Record<string, any>[]
  fields?: Record<string, any>
  risks?: Record<string, any>[]
  warnings?: string[]
}>()

const labels: Record<string, string> = {
  endometrium_thickness: '内膜厚度',
  endometrium_type: '内膜类型',
  right_ovary_size: '右卵巢大小',
  right_follicles: '右侧卵泡',
  left_ovary_size: '左卵巢大小',
  left_follicles: '左侧卵泡',
  remark: '备注',
  ultrasound_findings: '超声描述',
  ovary_size_candidate: '卵巢大小候选',
}

const cards = computed(() => {
  const groups: Record<string, { key: string; label: string; items: Record<string, any>[]; fields: any[]; review: boolean }> = {
    endometrium: { key: 'endometrium', label: '内膜段', items: [], fields: [], review: false },
    right: { key: 'right', label: '右卵巢段', items: [], fields: [], review: false },
    left: { key: 'left', label: '左卵巢段', items: [], fields: [], review: false },
    remark: { key: 'remark', label: '备注 / 其他医学描述', items: [], fields: [], review: false },
  }
  ;(props.segments || []).forEach((item) => {
    const field = String(item.field_code || '')
    let key = 'remark'
    if (field.startsWith('endometrium')) key = 'endometrium'
    else if (item.side === 'RIGHT' || field.startsWith('right_') || field === 'inferred_right_segment') key = 'right'
    else if (item.side === 'LEFT' || field.startsWith('left_') || field === 'inferred_left_segment') key = 'left'
    groups[key].items.push(item)
    if (String(item.note || '').includes('REVIEW') || String(item.note || '').includes('需复核') || String(item.note || '').includes('推断')) {
      groups[key].review = true
    }
  })

  const fields = props.fields || {}
  Object.entries(fields).forEach(([key, value]) => {
    let group = 'remark'
    if (key.startsWith('endometrium')) group = 'endometrium'
    else if (key.startsWith('right_')) group = 'right'
    else if (key.startsWith('left_')) group = 'left'
    groups[group].fields.push({ key, label: fieldLabel(key), value: format(value) })
  })

  ;(props.risks || []).forEach((risk: any) => {
    const field = String(risk.field_code || risk.field || '')
    let group = 'remark'
    if (field.startsWith('endometrium')) group = 'endometrium'
    else if (field.startsWith('right_')) group = 'right'
    else if (field.startsWith('left_')) group = 'left'
    groups[group].items.push({
      segment_type: 'risk',
      field_code: field,
      side: field.startsWith('right_') ? 'RIGHT' : field.startsWith('left_') ? 'LEFT' : '',
      text: risk.raw || risk.raw_text || risk.message || risk.rule_id || '风险校验',
      normalized: risk.converted || risk.suggestion || risk.action || '',
      note: `${risk.rule_id || '校验'} ${risk.action || ''} ${risk.message || risk.notes || ''}`.trim(),
    })
    if (['BLOCK', 'REVIEW', 'CANDIDATE'].includes(String(risk.action || ''))) groups[group].review = true
  })

  if ((props.warnings || []).length) {
    groups.remark.items.push(...(props.warnings || []).map((warning) => ({
      segment_type: 'warning', field_code: 'remark', side: '', text: warning, normalized: warning, note: '字段解析/风险校验警示',
    })))
    groups.remark.review = true
  }

  return Object.values(groups).filter((group) => group.items.length || group.fields.length)
})

function fieldLabel(value: string) { return labels[value] || value }
function sideLabel(value: string) { return value === 'RIGHT' ? '右侧' : value === 'LEFT' ? '左侧' : '侧别未知' }
function format(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((v) => typeof v === 'object' ? JSON.stringify(v) : String(v)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<style scoped>
.segment-wrap { display: grid; gap: 8px; }
.segment-title { font-weight: 600; }
.segment-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.segment-card { border: 1px solid #e8e8e8; border-radius: 8px; padding: 10px; min-width: 0; background: #fff; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.segment-row { padding: 8px 0; border-top: 1px dashed #eee; display: grid; gap: 4px; }
.segment-row:first-of-type { border-top: 0; }
.segment-meta { display: flex; gap: 4px; flex-wrap: wrap; }
.raw { font-size: 13px; line-height: 1.6; word-break: break-word; }
.normalized { font-size: 12px; color: #1677ff; }
.note { font-size: 12px; color: #8c8c8c; line-height: 1.5; }
.field-box { margin-top: 8px; padding-top: 8px; border-top: 1px solid #f0f0f0; }
.field-row { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; font-size: 13px; }
@media (max-width: 1100px) { .segment-grid { grid-template-columns: 1fr; } }
</style>
