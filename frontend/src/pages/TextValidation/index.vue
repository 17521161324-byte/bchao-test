<template>
  <div class="text-validation-page">
    <div class="page-head">
      <div>
        <h2>文本验证</h2>
        <div class="muted">ASR 优化方案 → LLM 完整纠错 → 规则提取 → 真实结果对比</div>
      </div>
      <a-space>
        <a-button @click="refreshAll">刷新</a-button>
        <a-button type="primary" :loading="running" :disabled="!canRunSelected" @click="runSelected">验证选中</a-button>
        <a-button :loading="runningAll" :disabled="!canRunAny" @click="runFiltered">验证当前筛选</a-button>
      </a-space>
    </div>

    <section class="panel config-panel">
      <a-row :gutter="[12, 12]" align="middle">
        <a-col :span="7">
          <div class="label">评估选择</div>
          <a-segmented v-model:value="selectedDate" :options="dateOptions" @change="loadScopeData" />
        </a-col>
        <a-col :span="5">
          <div class="label">ASR 方案</div>
          <a-select
            v-model:value="selectedPlanId"
            class="full"
            placeholder="选择优化评估历史方案"
            :options="planOptions"
            show-search
            option-filter-prop="label"
            @change="onPlanChange"
          />
        </a-col>
        <a-col :span="4">
          <div class="label">LLM 模型</div>
          <a-select v-model:value="form.llm_model_id" class="full" placeholder="LLM 模型" :options="llmOptions" />
        </a-col>
        <a-col :span="5">
          <div class="label">纠错模板</div>
          <a-input-group compact>
            <a-select v-model:value="form.correction_template_id" class="template-select" placeholder="纠错模板" :options="correctionTemplateOptions" />
            <a-button @click="openTemplateManager">维护</a-button>
          </a-input-group>
        </a-col>
        <a-col :span="3">
          <div class="label">规则库</div>
          <a-select v-model:value="form.rule_version_id" class="full" placeholder="规则" :options="ruleOptions" allow-clear />
        </a-col>
        <a-col :span="8">
          <a-input-search v-model:value="keyword" placeholder="搜索病历号" allow-clear />
        </a-col>
        <a-col :span="16">
          <a-space wrap>
            <a-tag v-if="selectedPlan" color="blue">{{ selectedPlan.name }}</a-tag>
            <a-tag v-if="selectedPlan">指纹 {{ selectedPlan.config_hash }}</a-tag>
            <a-tag color="green">当前筛选 {{ filteredRecords.length }} 条</a-tag>
            <a-tag color="cyan">可验证 {{ runnableRecords.length }} 条</a-tag>
            <a-tag color="orange">缺 ASR {{ missingAsrCount }} 条</a-tag>
          </a-space>
        </a-col>
      </a-row>
    </section>

    <div class="main-split">
      <section class="panel list-panel">
        <a-table
          size="small"
          row-key="id"
          :loading="loading"
          :columns="recordColumns"
          :data-source="tableRows"
          :row-selection="{ selectedRowKeys, onChange: onSelectionChange }"
          :pagination="{ pageSize: 18, showSizeChanger: false }"
          :custom-row="recordRow"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-tag v-if="record.matched_asr" color="blue">ASR</a-tag>
              <a-tag v-else>缺ASR</a-tag>
              <a-tag v-if="record.latest_run" :color="accuracyColor(record.latest_run.accuracy)">
                {{ percent(record.latest_run.accuracy) }}
              </a-tag>
            </template>
          </template>
        </a-table>
      </section>

      <section class="panel detail-panel">
        <a-empty v-if="!selectedRecord" description="请选择左侧检查记录" />
        <template v-else>
          <div class="detail-head">
            <a-space wrap>
              <a-tag color="blue">{{ selectedRecord.record_id }}</a-tag>
              <a-tag>{{ selectedRecord.date }}</a-tag>
              <a-tag>{{ selectedRecord.segs?.length || 0 }} 段录音</a-tag>
              <a-tag>{{ selectedRecord.has_result ? '有真实结果' : '无真实结果' }}</a-tag>
              <a-tag v-if="selectedRecord.matched_asr">{{ selectedRecord.matched_asr.asr_model_name || selectedRecord.matched_asr.provider }}</a-tag>
              <a-tag v-if="currentRun" :color="accuracyColor(currentRun.accuracy)">准确率 {{ percent(currentRun.accuracy) }}</a-tag>
            </a-space>
            <a-button size="small" type="primary" :disabled="!selectedRecord.matched_asr || running || !canRunAny" @click="runOne(selectedRecord)">
              验证当前
            </a-button>
          </div>

          <a-tabs v-model:activeKey="activeTab">
            <a-tab-pane key="current" tab="当前结果">
              <a-alert
                v-if="currentRun?.status === 'failed'"
                type="error"
                show-icon
                :message="currentRun.error_message || '验证失败'"
                class="run-alert"
              />
              <a-empty v-if="!currentRun" description="暂无验证结果" />
              <div v-else class="validation-workbench">
                <div class="text-card">
                  <div class="card-title">原始 ASR</div>
                  <pre>{{ currentRun.raw_asr_text || '-' }}</pre>
                </div>

                <div class="text-card">
                  <div class="card-title">
                    标注 ASR 转写结果
                    <span class="legend">
                      <span class="legend-item mark-endometrium">内膜</span>
                      <span class="legend-item mark-right">右卵巢/右卵泡</span>
                      <span class="legend-item mark-left">左卵巢/左卵泡</span>
                    </span>
                  </div>
                  <pre class="annotated-text"><template v-for="(part, index) in highlightedCorrectedText" :key="index"><span :class="part.className">{{ part.text }}</span></template></pre>
                </div>

                <div class="text-card">
                  <div class="card-title">
                    标准 ASR 文本
                    <a-tag :color="selectedAsrReference?.reference_text ? 'purple' : 'default'">
                      {{ selectedAsrReference?.reference_text ? '已保存' : '未配置' }}
                    </a-tag>
                  </div>
                  <div class="embedded-audio">
                    <AudioPlayer v-if="selectedRecord.segs?.length" :segs="selectedRecord.segs" />
                    <a-empty v-else description="暂无录音" />
                  </div>
                  <pre class="reference-text">{{ selectedAsrReference?.reference_text || '暂无标准 ASR 文本，请先在优化评估/ASR 转化评估中维护该检查记录的标准 ASR。' }}</pre>
                </div>

                <div class="text-card">
                  <div class="card-title">真实结果对比</div>
                  <a-table size="small" :columns="evaluationColumns" :data-source="evaluationRows" :pagination="false">
                    <template #bodyCell="{ column, record }">
                      <template v-if="column.key === 'mismatch_details'">
                        <div v-if="record.mismatchDetails" class="follicle-mismatch">
                          <div v-if="record.mismatchDetails.missing" class="mismatch-missing">漏识别：{{ record.mismatchDetails.missing }}</div>
                          <div v-if="record.mismatchDetails.extra" class="mismatch-extra">多识别：{{ record.mismatchDetails.extra }}</div>
                        </div>
                        <span v-else class="muted">-</span>
                      </template>
                    </template>
                  </a-table>
                </div>

                <div class="text-card">
                  <div class="card-title">命中规则（{{ currentRun.conversions?.length || 0 }}）</div>
                  <a-table
                    v-if="currentRun.conversions?.length"
                    size="small"
                    row-key="cidx"
                    :columns="conversionColumns"
                    :data-source="conversionRows"
                    :pagination="false"
                    :scroll="{ y: 220 }"
                  />
                  <span v-else class="muted">无命中规则</span>
                </div>

                <div class="text-card">
                  <div class="card-title">业务片段（{{ currentRun.segments?.length || 0 }}）</div>
                  <a-table
                    v-if="currentRun.segments?.length"
                    size="small"
                    row-key="sidx"
                    :columns="segmentColumns"
                    :data-source="segmentRows"
                    :pagination="false"
                    :scroll="{ y: 220 }"
                  />
                  <span v-else class="muted">未定位到业务片段</span>
                </div>

                <div class="text-card full-row">
                  <div class="card-title">规则警示（{{ currentRun.risk_items?.length || 0 }}）</div>
                  <a-table
                    v-if="currentRun.risk_items?.length"
                    size="small"
                    row-key="ridx"
                    :columns="riskColumns"
                    :data-source="riskRows"
                    :pagination="false"
                  />
                  <a-alert v-else type="success" show-icon message="未命中警示规则" />
                </div>
              </div>
            </a-tab-pane>

            <a-tab-pane key="history" tab="历史结果">
              <a-table size="small" row-key="id" :columns="historyColumns" :data-source="historyRuns" :pagination="{ pageSize: 10 }">
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'accuracy'">
                    <a-tag :color="accuracyColor(record.accuracy)">{{ percent(record.accuracy) }}</a-tag>
                  </template>
                  <template v-else-if="column.key === 'operate'">
                    <a-button type="link" size="small" @click="currentRun = record; activeTab = 'current'">查看</a-button>
                  </template>
                </template>
              </a-table>
            </a-tab-pane>
          </a-tabs>
        </template>
      </section>
    </div>

    <a-modal
      v-model:open="templateModalOpen"
      title="纠错模板维护"
      width="900px"
      :footer="null"
    >
      <div class="template-manager">
        <div class="template-list">
          <a-button type="primary" block @click="openTemplateForm()">新增模板</a-button>
          <a-list size="small" :data-source="correctionTemplates">
            <template #renderItem="{ item }">
              <a-list-item :class="{ active: editingTemplate?.id === item.id }" @click="openTemplateForm(item)">
                <a-list-item-meta>
                  <template #title>
                    {{ item.name }}
                    <a-tag v-if="item.is_default" color="green">默认</a-tag>
                  </template>
                  <template #description>{{ item.status }}</template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </div>
        <div class="template-form">
          <a-form layout="vertical">
            <a-form-item label="模板名称"><a-input v-model:value="templateForm.name" /></a-form-item>
            <a-form-item label="模板内容">
              <a-textarea v-model:value="templateForm.content" :rows="13" />
            </a-form-item>
            <a-space>
              <a-checkbox v-model:checked="templateForm.is_default">设为默认</a-checkbox>
              <a-button type="primary" @click="saveTemplate">保存</a-button>
              <a-popconfirm v-if="editingTemplate" title="确认删除该纠错模板？" @confirm="deleteTemplate">
                <a-button danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </a-form>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  asrOptimizationApi,
  audioApi,
  conversionConfigApi,
  modelApi,
  patientApi,
  textValidationApi,
} from '@/api/client'
import AudioPlayer from '@/components/AudioPlayer/index.vue'

const loading = ref(false)
const running = ref(false)
const runningAll = ref(false)
const selectedDate = ref('全部')
const keyword = ref('')
const records = ref<any[]>([])
const selectedRecord = ref<any | null>(null)
const selectedRowKeys = ref<number[]>([])
const selectedPlanId = ref<number | undefined>()
const plans = ref<any[]>([])
const asrResultsByRecord = ref<Record<string, any[]>>({})
const asrReferencesByRecord = ref<Record<string, any | null>>({})
const latestRunsByRecord = ref<Record<string, any>>({})
const llmModels = ref<any[]>([])
const correctionTemplates = ref<any[]>([])
const ruleVersions = ref<any[]>([])
const historyRuns = ref<any[]>([])
const currentRun = ref<any | null>(null)
const activeTab = ref('current')
const templateModalOpen = ref(false)
const editingTemplate = ref<any | null>(null)
const templateForm = reactive({ name: '', content: '', is_default: false })

const form = reactive({
  llm_model_id: undefined as number | undefined,
  correction_template_id: undefined as number | undefined,
  rule_version_id: undefined as number | undefined,
})

const selectedPlan = computed(() => plans.value.find((item) => item.id === selectedPlanId.value))
const selectedAsrReference = computed(() => {
  if (!selectedRecord.value) return null
  return asrReferencesByRecord.value[String(selectedRecord.value.id)] || null
})
const dateOptions = computed(() => ['全部', ...Array.from(new Set(records.value.map((item) => item.date).filter(Boolean))).sort().reverse()])

const filteredRecords = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return records.value.filter((item) => {
    if (selectedDate.value !== '全部' && item.date !== selectedDate.value) return false
    if (q && !String(item.record_id || '').toLowerCase().includes(q)) return false
    return true
  })
})

const tableRows = computed(() => filteredRecords.value.map((record) => {
  const matchedAsr = findMatchedAsr(record.id)
  return {
    ...record,
    matched_asr: matchedAsr,
    latest_run: latestRunsByRecord.value[String(record.id)] || null,
  }
}))

const runnableRecords = computed(() => tableRows.value.filter((record) => record.matched_asr))
const missingAsrCount = computed(() => filteredRecords.value.length - runnableRecords.value.length)
const planOptions = computed(() => plans.value.map((item) => ({ value: item.id, label: item.name })))
const llmOptions = computed(() => llmModels.value.map((item) => ({ value: item.id, label: item.name })))
const correctionTemplateOptions = computed(() => correctionTemplates.value.map((item) => ({ value: item.id, label: item.name })))
const ruleOptions = computed(() => ruleVersions.value.map((item) => ({
  value: item.id,
  label: `${item.version_name || item.version_code} · ${item.status}`,
})))
const canRunAny = computed(() => !!selectedPlan.value && !!form.llm_model_id && !!form.correction_template_id && runnableRecords.value.length > 0)
const canRunSelected = computed(() => canRunAny.value && selectedRowKeys.value.length > 0)

const recordColumns = [
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', width: 100 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 92 },
  { title: '状态', key: 'status', width: 150 },
]
const evaluationColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 140 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 80 },
  { title: '提取值', dataIndex: 'identified', key: 'identified' },
  { title: '真实值', dataIndex: 'truth', key: 'truth' },
  { title: '错漏数据', dataIndex: 'mismatchText', key: 'mismatch_details', width: 230 },
]
const historyColumns = [
  { title: '时间', dataIndex: 'created_at', key: 'created_at', customRender: ({ text }: any) => formatTime(text) },
  { title: 'ASR', dataIndex: 'asr_model_name', key: 'asr_model_name' },
  { title: 'LLM', dataIndex: 'llm_model_name', key: 'llm_model_name' },
  { title: '纠错模板', dataIndex: 'prompt_template_name', key: 'prompt_template_name' },
  { title: '规则', dataIndex: 'rule_version', key: 'rule_version' },
  { title: '准确率', dataIndex: 'accuracy', key: 'accuracy' },
  { title: '操作', key: 'operate', width: 80 },
]
const conversionColumns = [
  { title: '规则', dataIndex: 'rule_id', key: 'rule_id', width: 100 },
  { title: '原文', dataIndex: 'raw', key: 'raw', width: 180 },
  { title: '转化', dataIndex: 'converted', key: 'converted', width: 180 },
  { title: '动作', dataIndex: 'action', key: 'action', width: 100 },
]
const segmentColumns = [
  { title: '类型', dataIndex: 'segment_type', key: 'segment_type', width: 110 },
  { title: '字段', dataIndex: 'field_code', key: 'field_code', width: 170 },
  { title: '侧别', dataIndex: 'side', key: 'side', width: 70 },
  { title: '原文', dataIndex: 'text', key: 'text', width: 140 },
  { title: '归一', dataIndex: 'normalized', key: 'normalized', width: 120 },
]
const riskColumns = [
  { title: '规则', dataIndex: 'rule_id', key: 'rule_id', width: 90 },
  { title: '动作', dataIndex: 'action', key: 'action', width: 100 },
  { title: '严重度', dataIndex: 'severity', key: 'severity', width: 100 },
  { title: '提示', dataIndex: 'message', key: 'message' },
]

const fieldLabels: Record<string, string> = {
  right_follicle_total: '右卵泡总数',
  left_follicle_total: '左卵泡总数',
  right_follicles: '右卵泡明细',
  left_follicles: '左卵泡明细',
  endometrium_thickness: '内膜厚度',
  endometrium_type: '内膜类型',
  right_ovary_length: '右卵巢长',
  right_ovary_width: '右卵巢宽',
  left_ovary_length: '左卵巢长',
  left_ovary_width: '左卵巢宽',
  remark: '备注',
}

const evaluationRows = computed(() => {
  const fields = currentRun.value?.evaluation?.fields || {}
  return Object.entries(fields).map(([key, value]: any) => ({
    key,
    label: fieldLabels[key] || key,
    status: value.match ? '✅' : '❌',
    identified: formatValue(value.identified),
    truth: formatValue(value.truth),
    mismatchDetails: follicleMismatchDetails(key, value.identified, value.truth),
  }))
})
const highlightedCorrectedText = computed(() => buildHighlightedText(
  currentRun.value?.corrected_text || '',
  currentRun.value?.source_spans || [],
))
const conversionRows = computed(() => (currentRun.value?.conversions || []).map((item: any, idx: number) => ({ ...item, cidx: idx + 1 })))
const segmentRows = computed(() => (currentRun.value?.segments || []).map((item: any, idx: number) => ({ ...item, sidx: idx + 1 })))
const riskRows = computed(() => (currentRun.value?.risk_items || []).map((item: any, idx: number) => ({ ...item, ridx: idx + 1 })))

function findMatchedAsr(recordId: number) {
  const rows = asrResultsByRecord.value[String(recordId)] || []
  const hash = selectedPlan.value?.config_hash
  if (!hash) return null
  return rows.find((item) => item.config_hash === hash && item.status === 'success' && item.full_transcript) || null
}

function recordRow(record: any) {
  return { onClick: () => selectRecord(record), class: record.id === selectedRecord.value?.id ? 'selected-row' : '' }
}
function onSelectionChange(keys: number[]) { selectedRowKeys.value = keys }
function formatTime(value: string) { return value ? String(value).replace('T', ' ').slice(0, 16) : '-' }
function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item) => `${item.size}×${item.count}`).join('、') || '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
function normalizeFollicleList(value: any[]) {
  const bucket = new Map<string, { size: number; count: number }>()
  ;(Array.isArray(value) ? value : []).forEach((item: any) => {
    const size = Number(item?.size)
    const count = Number(item?.count ?? 1)
    if (!Number.isFinite(size) || !Number.isFinite(count) || count <= 0) return
    const key = String(size)
    const current = bucket.get(key) || { size, count: 0 }
    current.count += count
    bucket.set(key, current)
  })
  return bucket
}
function formatFollicleBucket(items: Array<{ size: number; count: number }>) {
  return items
    .sort((a, b) => b.size - a.size)
    .map((item) => `${item.size}×${item.count}`)
    .join('；')
}
function follicleMismatchDetails(fieldKey: string, identified: any, truth: any) {
  if (!['right_follicles', 'left_follicles'].includes(fieldKey)) return null
  const identifiedMap = normalizeFollicleList(identified)
  const truthMap = normalizeFollicleList(truth)
  const sizes = new Set([...identifiedMap.keys(), ...truthMap.keys()])
  const missing: Array<{ size: number; count: number }> = []
  const extra: Array<{ size: number; count: number }> = []
  sizes.forEach((sizeKey) => {
    const identifiedItem = identifiedMap.get(sizeKey)
    const truthItem = truthMap.get(sizeKey)
    const identifiedCount = identifiedItem?.count || 0
    const truthCount = truthItem?.count || 0
    const size = truthItem?.size ?? identifiedItem?.size ?? Number(sizeKey)
    if (truthCount > identifiedCount) missing.push({ size, count: truthCount - identifiedCount })
    if (identifiedCount > truthCount) extra.push({ size, count: identifiedCount - truthCount })
  })
  const missingText = formatFollicleBucket(missing)
  const extraText = formatFollicleBucket(extra)
  if (!missingText && !extraText) return null
  return { missing: missingText, extra: extraText }
}
function percent(value: any) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Math.round(Number(value) * 1000) / 10}%`
}
function accuracyColor(value: any) {
  const n = Number(value || 0)
  if (n >= 0.9) return 'green'
  if (n >= 0.7) return 'orange'
  return 'red'
}
function fieldClass(fieldCode: string) {
  if (fieldCode.startsWith('endometrium')) return 'mark-endometrium'
  if (fieldCode.startsWith('right_')) return 'mark-right'
  if (fieldCode.startsWith('left_')) return 'mark-left'
  return ''
}
function buildHighlightedText(text: string, spans: any[]) {
  if (!text) return [{ text: '-', className: '' }]
  const validSpans = (Array.isArray(spans) ? spans : [])
    .map((span) => realignHighlightSpan(text, span))
    .filter((span) => span.className && Number.isFinite(span.start) && Number.isFinite(span.end) && span.end > span.start)
    .map((span) => ({
      ...span,
      start: Math.max(0, Math.min(span.start, text.length)),
      end: Math.max(0, Math.min(span.end, text.length)),
    }))
    .sort((a, b) => a.start - b.start || b.end - a.end)

  const parts: Array<{ text: string; className: string }> = []
  let cursor = 0
  for (const span of validSpans) {
    if (span.start < cursor) continue
    if (span.start > cursor) parts.push({ text: text.slice(cursor, span.start), className: '' })
    parts.push({ text: text.slice(span.start, span.end), className: span.className })
    cursor = span.end
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), className: '' })
  return parts.length ? parts : [{ text, className: '' }]
}
function realignHighlightSpan(text: string, span: any) {
  let start = Number(span.start)
  let end = Number(span.end)
  const rawText = String(span.raw_text || '')
  const className = fieldClass(String(span.field_code || ''))
  if (rawText && text.slice(start, end) !== rawText) {
    const windowStart = Math.max(0, start - 8)
    const windowEnd = Math.min(text.length, end + 8)
    const localIndex = text.slice(windowStart, windowEnd).indexOf(rawText)
    const globalIndex = localIndex >= 0 ? windowStart + localIndex : text.indexOf(rawText)
    if (globalIndex >= 0) {
      start = globalIndex
      end = globalIndex + rawText.length
    }
  }
  return { start, end, className }
}

async function refreshAll() {
  loading.value = true
  try {
    const [recordData, llmData, templateData, versionData, planData]: any[] = await Promise.all([
      audioApi.getRecords(),
      modelApi.list('llm'),
      textValidationApi.listCorrectionTemplates(),
      conversionConfigApi.listVersions(),
      asrOptimizationApi.listPlans(),
    ])
    records.value = recordData || []
    llmModels.value = (llmData || []).filter((item: any) => item.status === 'active')
    correctionTemplates.value = templateData || []
    ruleVersions.value = versionData || []
    plans.value = planData || []
    if (!selectedPlanId.value && plans.value.length) selectedPlanId.value = plans.value[0].id
    if (!form.llm_model_id) form.llm_model_id = llmModels.value.find((item) => item.is_default)?.id || llmModels.value[0]?.id
    if (!form.correction_template_id) form.correction_template_id = correctionTemplates.value.find((item) => item.is_default)?.id || correctionTemplates.value[0]?.id
    await loadScopeData()
  } finally {
    loading.value = false
  }
}

async function loadScopeData() {
  selectedRowKeys.value = []
  const ids = filteredRecords.value.map((record) => record.id)
  if (!ids.length) {
    asrResultsByRecord.value = {}
    asrReferencesByRecord.value = {}
    latestRunsByRecord.value = {}
    selectedRecord.value = null
    currentRun.value = null
    return
  }
  const [asrData, referenceData, validationData]: any[] = await Promise.all([
    patientApi.listAsrResultsBatch(ids),
    patientApi.listAsrReferencesBatch(ids),
    textValidationApi.listRuns({ limit: 500 }),
  ])
  asrResultsByRecord.value = asrData || {}
  asrReferencesByRecord.value = referenceData || {}
  const idSet = new Set(ids.map(String))
  const latest: Record<string, any> = {}
  ;(validationData || []).forEach((run: any) => {
    const key = String(run.exam_record_id)
    if (idSet.has(key) && !latest[key]) latest[key] = run
  })
  latestRunsByRecord.value = latest
  const first = tableRows.value.find((item) => item.id === selectedRecord.value?.id) || tableRows.value[0]
  selectedRecord.value = first || null
  if (first) await loadRecordHistory(first)
}

async function onPlanChange() {
  currentRun.value = null
  await loadScopeData()
}
async function selectRecord(record: any) {
  selectedRecord.value = record
  await loadRecordHistory(record)
}
async function loadRecordHistory(record: any) {
  const history: any[] = await textValidationApi.listRuns({ exam_record_id: record.id, limit: 50 })
  historyRuns.value = history || []
  currentRun.value = historyRuns.value[0] || null
}

function validationPayload(record: any, matchedAsr: any) {
  return {
    exam_record_id: record.id,
    asr_result_id: matchedAsr.id,
    llm_model_id: form.llm_model_id,
    correction_template_id: form.correction_template_id,
    rule_version_id: form.rule_version_id,
    rule_version: selectedPlan.value?.name || 'manual',
  }
}
async function runOne(record: any) {
  const matchedAsr = record.matched_asr || findMatchedAsr(record.id)
  if (!matchedAsr || !form.llm_model_id || !form.correction_template_id) return
  running.value = true
  try {
    const run: any = await textValidationApi.createRun(validationPayload(record, matchedAsr))
    latestRunsByRecord.value[String(record.id)] = run
    await loadRecordHistory(record)
    currentRun.value = run
    activeTab.value = 'current'
    message.success(run.status === 'success' ? `${record.record_id} 验证完成` : `${record.record_id} 验证失败，已保存错误`)
  } finally {
    running.value = false
  }
}
async function runSelected() {
  await runBatch(tableRows.value.filter((record) => selectedRowKeys.value.includes(record.id) && record.matched_asr))
}
async function runFiltered() { await runBatch(runnableRecords.value) }
async function runBatch(rows: any[]) {
  if (!rows.length) return
  runningAll.value = true
  try {
    let ok = 0
    for (const record of rows) {
      const matchedAsr = record.matched_asr || findMatchedAsr(record.id)
      if (!matchedAsr || !form.llm_model_id || !form.correction_template_id) continue
      const run: any = await textValidationApi.createRun(validationPayload(record, matchedAsr))
      latestRunsByRecord.value[String(record.id)] = run
      if (run.status === 'success') ok += 1
    }
    if (selectedRecord.value) await loadRecordHistory(selectedRecord.value)
    message.success(`完成 ${ok}/${rows.length} 条验证`)
  } finally {
    runningAll.value = false
  }
}

function openTemplateManager() {
  templateModalOpen.value = true
  openTemplateForm(correctionTemplates.value.find((item) => item.id === form.correction_template_id) || correctionTemplates.value[0])
}
function openTemplateForm(item?: any) {
  editingTemplate.value = item || null
  templateForm.name = item?.name || ''
  templateForm.content = item?.content || ''
  templateForm.is_default = !!item?.is_default
}
async function saveTemplate() {
  if (!templateForm.name.trim() || !templateForm.content.includes('{transcript}')) {
    message.error('模板名称不能为空，内容必须包含 {transcript}')
    return
  }
  if (editingTemplate.value) {
    await textValidationApi.updateCorrectionTemplate(editingTemplate.value.id, templateForm)
  } else {
    await textValidationApi.createCorrectionTemplate(templateForm)
  }
  correctionTemplates.value = await textValidationApi.listCorrectionTemplates() as any[]
  if (!form.correction_template_id) form.correction_template_id = correctionTemplates.value[0]?.id
  message.success('模板已保存')
}
async function deleteTemplate() {
  if (!editingTemplate.value) return
  await textValidationApi.deleteCorrectionTemplate(editingTemplate.value.id)
  correctionTemplates.value = await textValidationApi.listCorrectionTemplates() as any[]
  form.correction_template_id = correctionTemplates.value.find((item) => item.is_default)?.id || correctionTemplates.value[0]?.id
  openTemplateForm(correctionTemplates.value[0])
  message.success('模板已删除')
}

onMounted(refreshAll)
</script>

<style scoped>
.text-validation-page { padding: 16px; }
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.page-head h2 { margin: 0; font-size: 20px; }
.muted { color: #888; font-size: 13px; }
.panel {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  min-width: 0;
}
.config-panel { margin-bottom: 12px; }
.main-split {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  gap: 12px;
}
.list-panel,
.detail-panel {
  height: calc(100vh - 210px);
  overflow: auto;
}
.label {
  color: #666;
  font-size: 12px;
  margin-bottom: 6px;
}
.full { width: 100%; }
.template-select { width: calc(100% - 58px); }
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.run-alert { margin-bottom: 12px; }
.validation-workbench {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.text-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  min-width: 0;
}
.full-row { grid-column: 1 / -1; }
.embedded-audio {
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f0f0f0;
}
.reference-text {
  min-height: 160px;
  color: #444;
  background: #fafafa;
  border-radius: 4px;
  padding: 10px;
}
.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 10px;
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 360px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
}
.annotated-text span {
  border-radius: 3px;
  padding: 1px 2px;
}
.mark-endometrium {
  color: #0958d9;
  background: #e6f4ff;
  font-weight: 600;
}
.mark-right {
  color: #d4380d;
  background: #fff2e8;
  font-weight: 600;
}
.mark-left {
  color: #389e0d;
  background: #f6ffed;
  font-weight: 600;
}
.legend {
  display: inline-flex;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
  font-weight: 400;
}
.legend-item {
  border: 1px solid currentColor;
  border-radius: 10px;
  padding: 1px 7px;
}
.follicle-mismatch {
  line-height: 1.7;
  white-space: normal;
}
.mismatch-missing {
  color: #d46b08;
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 4px;
  padding: 2px 6px;
  margin-bottom: 3px;
}
.mismatch-extra {
  color: #cf1322;
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 4px;
  padding: 2px 6px;
}
.template-manager {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 14px;
}
.template-list {
  border-right: 1px solid #f0f0f0;
  padding-right: 12px;
}
.template-list :deep(.ant-list-item) { cursor: pointer; }
.template-list :deep(.ant-list-item.active) { background: #e6f4ff; }
:deep(.selected-row td) { background: #e6f4ff !important; }
:deep(.ant-table-row) { cursor: pointer; }
</style>
