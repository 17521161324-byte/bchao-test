<template>
  <div class="diag-wrap">
    <div class="diag-head">
      <strong>本步骤规则执行诊断</strong>
      <a-space size="small" wrap>
        <a-tag>已配置 {{ stats.configured }}</a-tag>
        <a-tag color="blue">已调用 {{ stats.called }}</a-tag>
        <a-tag color="green">命中 {{ stats.hit }}</a-tag>
        <a-button size="small" :loading="loading" @click="loadRules">刷新规则配置</a-button>
      </a-space>
    </div>
    <a-alert
      v-if="loadError"
      type="warning"
      show-icon
      :message="loadError"
      description="仍会展示本次执行真实产生的规则记录，但“已配置”状态可能无法完全确认。"
      class="diag-alert"
    />
    <a-table
      size="small"
      row-key="key"
      :columns="columns"
      :data-source="rows"
      :pagination="{ pageSize: 12, showSizeChanger: false }"
      :loading="loading"
      class="diag-table"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'configured'">
          <a-tag :color="record.configured === '是' ? 'green' : record.configured === '未知' ? 'default' : 'red'">{{ record.configured }}</a-tag>
        </template>
        <template v-else-if="column.key === 'called'">
          <a-tag :color="record.called ? 'blue' : 'default'">{{ record.called ? '是' : '否' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'hit'">
          <a-tag :color="record.hit ? 'green' : 'default'">{{ record.hit ? '是' : '否' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'action'">
          <a-tag v-if="record.action" :color="actionColor(record.action)">{{ record.action }}</a-tag>
          <span v-else>-</span>
        </template>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { conversionConfigApi } from '@/api/client'
import type { PipelineStep } from '@/types/conversionPipeline'

const props = defineProps<{
  steps: PipelineStep[]
  ruleVersionId?: number | null
}>()

const loading = ref(false)
const loadError = ref('')
const configuredRules = ref<Record<string, any>[]>([])

const columns = [
  { title: '规则ID', dataIndex: 'rule_id', key: 'rule_id', width: 120 },
  { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name', width: 180, ellipsis: true },
  { title: '已配置', key: 'configured', width: 82 },
  { title: '已调用', key: 'called', width: 82 },
  { title: '命中', key: 'hit', width: 72 },
  { title: '动作', key: 'action', width: 92 },
  { title: '命中文本', dataIndex: 'hit_text', key: 'hit_text', width: 180, ellipsis: true },
  { title: '输出变化', dataIndex: 'output_change', key: 'output_change', width: 200, ellipsis: true },
  { title: '判定依据', dataIndex: 'reason', key: 'reason', ellipsis: true },
]

const observed = computed(() => {
  const map = new Map<string, Record<string, any>>()
  ;(props.steps || []).forEach((step) => {
    ;[...(step.rule_hits || []), ...(step.conversions || [])].forEach((item: any, idx) => {
      const explicit = String(item.rule_id || item.rule_code || '').trim()
      const fromNote = String(item.note || item.notes || '').match(/\b([A-Z]+\d{3}(?:\+[A-Z]+\d{3})?)\b/)?.[1] || ''
      const id = explicit || fromNote
      if (!id) return
      const existing = map.get(id) || {}
      map.set(id, {
        ...existing,
        ...item,
        rule_id: id,
        step_code: step.step_code,
        _idx: idx,
      })
    })
  })
  return map
})

const rows = computed(() => {
  const selectedCodes = new Set((props.steps || []).map((step) => step.step_code))
  const configLoadSucceeded = !loadError.value
  const map = new Map<string, Record<string, any>>()

  configuredRules.value.forEach((rule) => {
    const id = ruleId(rule)
    if (!id) return
    const code = ruleStep(rule, id)
    if (code && !selectedCodes.has(code)) return
    const hit = observed.value.get(id)
    const called = !!code && (props.steps || []).some((step) => step.step_code === code && step.status !== 'pending')
    map.set(id, makeRow(id, rule, hit, called, '是'))
  })

  observed.value.forEach((hit, id) => {
    if (map.has(id)) return
    const code = String(hit.step_code || ruleStep(hit, id) || '')
    if (code && !selectedCodes.has(code)) return
    map.set(id, makeRow(id, null, hit, true, configLoadSucceeded ? '否' : '未知'))
  })

  return Array.from(map.values()).sort((a, b) => String(a.rule_id).localeCompare(String(b.rule_id), 'zh-CN'))
})

const stats = computed(() => ({
  configured: rows.value.filter((row) => row.configured === '是').length,
  called: rows.value.filter((row) => row.called).length,
  hit: rows.value.filter((row) => row.hit).length,
}))

function unwrap(value: any): any[] {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.items)) return value.items
  if (Array.isArray(value?.data)) return value.data
  if (value && typeof value === 'object') {
    return Object.values(value).flatMap((item: any) => Array.isArray(item) ? item : [])
  }
  return []
}

function ruleId(rule: any) {
  return String(rule?.rule_id || rule?.rule_code || rule?.code || '').trim()
}

function ruleStep(rule: any, id: string) {
  const explicit = String(rule?.step_code || rule?.step || '').toUpperCase()
  if (explicit) return explicit
  if (/^C\d+/.test(id)) return 'MEDICAL_TERM'
  if (/^(D|N)\d+/.test(id)) return 'NUMBER_NORMALIZE'
  if (/^(S|BS_)\w*/.test(id)) return 'BUSINESS_SEGMENT'
  if (/^M\d+/.test(id)) return 'FIELD_PARSE'
  if (/^F\d+/.test(id)) return 'FIELD_PARSE'
  if (/^R\d+/.test(id)) return 'RISK_INTERCEPT'
  return ''
}

function makeRow(id: string, rule: any, hit: any, called: boolean, configured: string) {
  const raw = hit?.raw ?? hit?.raw_text ?? hit?.text ?? hit?.term ?? ''
  const converted = hit?.converted ?? hit?.normalized ?? hit?.target ?? ''
  return {
    key: id,
    rule_id: id,
    rule_name: rule?.rule_name || rule?.name || rule?.notes || rule?.standard || rule?.standard_text ||
      (rule?.asr_error && rule?.standard ? `${rule.asr_error} → ${rule.standard}` : '') ||
      hit?.rule_name || hit?.name || id,
    configured,
    called,
    hit: !!hit,
    action: hit?.action || rule?.action || '',
    hit_text: raw ? String(raw) : '-',
    output_change: converted !== '' && String(converted) !== String(raw) ? `${raw || '-'} → ${format(converted)}` : (hit ? '生成候选/上下文元数据' : '-'),
    reason: hit?.message || hit?.notes || hit?.note || hit?.evidence || rule?.notes || '-',
  }
}

function format(value: any) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function actionColor(action: string) {
  return ({ AUTO: 'green', CANDIDATE: 'blue', REVIEW: 'orange', BLOCK: 'red', WARN: 'gold' } as Record<string, string>)[action] || 'default'
}

async function loadRules() {
  loading.value = true
  loadError.value = ''
  try {
    const tasks: Array<{ source: 'builtin' | 'lexicon' | 'runtime'; promise: Promise<any> }> = [
      { source: 'builtin', promise: conversionConfigApi.listBuiltinRules() },
    ]
    if (props.ruleVersionId) {
      tasks.push({ source: 'lexicon', promise: conversionConfigApi.listLexicon(props.ruleVersionId) })
      tasks.push({ source: 'runtime', promise: conversionConfigApi.listRules(props.ruleVersionId) })
    }
    const settled = await Promise.allSettled(tasks.map((item) => item.promise))
    const merged: any[] = []
    settled.forEach((result, index) => {
      if (result.status !== 'fulfilled') return
      const source = tasks[index].source
      unwrap(result.value).forEach((rule: any) => merged.push({
        ...rule,
        step_code: rule?.step_code || (source === 'lexicon' ? 'MEDICAL_TERM' : source === 'runtime' ? 'RUNTIME_RULE' : undefined),
      }))
    })
    configuredRules.value = merged
    if (settled.some((result) => result.status === 'rejected')) {
      loadError.value = '部分规则配置读取失败'
    }
  } catch {
    configuredRules.value = []
    loadError.value = '规则配置读取失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.ruleVersionId, loadRules)
onMounted(loadRules)
</script>

<style scoped>
.diag-wrap { display: grid; gap: 8px; margin-top: 12px; }
.diag-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
.diag-alert { margin-bottom: 2px; }
.diag-table :deep(.ant-table-cell) { vertical-align: top; }
</style>
