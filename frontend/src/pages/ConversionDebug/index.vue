<template>
  <div class="app">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="brand">
        <span class="brand-logo">AI</span>
        <div class="brand-text">
          <div class="brand-title">ASR 转化调试</div>
          <div class="brand-sub">按真实历史 ASR 逐步诊断医学名词 / 数值 / 业务片段 / 字段解析的规则执行过程</div>
        </div>
      </div>
      <div class="topbar-right">
        <a-tag color="purple" class="rule-tag">当前讨论规则：{{ currentRuleLabel }}</a-tag>
      </div>
    </header>

    <div class="layout">
      <!-- 左侧：ASR 指纹与文本记录 -->
      <DebugSidebar
        :records="sidebarRecords"
        :selected-id="selectedId"
        :loading="loadingRecords"
        :batch-running="batchRunning"
        @select="onSelectRecord"
        @batch="onBatchRun"
      />

      <!-- 右侧：记录诊断 -->
      <main class="main">
        <template v-if="selectedRecord">
          <!-- 记录信息头 -->
          <div class="panel record-head">
            <div class="record-head-left">
              <div class="record-head-line1">
                <span class="record-title">ASR结果ID {{ selectedRecord.id }}</span>
                <a-tag>原始ASR</a-tag>
                <a-tag :color="statusTagColor[selectedRecord.status]">{{ statusTagLabel[selectedRecord.status] }}</a-tag>
              </div>
              <div class="record-head-line2">
                记录指纹：<code class="hash-text">{{ selectedRecord.config_hash || '无配置指纹' }}</code>
              </div>
            </div>
            <a-space>
              <a-tooltip title="基于该历史 ASR 文本执行完整流水线（真实调用后端）">
                <a-button type="primary" :loading="executing" @click="executeCurrent">执行当前规则</a-button>
              </a-tooltip>
              <a-tooltip title="处理状态由最新一次流水线执行的 result_level 自动推导，后端暂未提供手动更新接口">
                <a-button disabled>更新处理状态</a-button>
              </a-tooltip>
            </a-space>
          </div>

          <!-- 六宫格 patient-strip -->
          <div class="patient-strip">
            <div class="strip-item">
              <div class="strip-label">病历号</div>
              <div class="strip-value">{{ selectedRecord.record_id || '-' }}</div>
            </div>
            <div class="strip-item">
              <div class="strip-label">检查日期</div>
              <div class="strip-value">{{ selectedRecord.date || '-' }}</div>
            </div>
            <div class="strip-item">
              <div class="strip-label">ASR方案</div>
              <div class="strip-value">{{ selectedRecord.asr_model_name || '-' }}</div>
            </div>
            <div class="strip-item">
              <div class="strip-label">文本来源</div>
              <div class="strip-value">{{ inputSourceLabel }}</div>
            </div>
            <div class="strip-item">
              <div class="strip-label">最近执行时间</div>
              <div class="strip-value">{{ latestExecutionTime }}</div>
            </div>
            <div class="strip-item">
              <div class="strip-label">真实结果</div>
              <div class="strip-value">
                <a-tag :color="hasTruth ? 'green' : 'default'">{{ hasTruth ? '已维护' : '未维护' }}</a-tag>
              </div>
            </div>
          </div>

          <!-- 原始ASR文本 -->
          <div class="panel raw-panel">
            <div class="raw-title">原始ASR文本</div>
            <pre class="raw-text">{{ selectedRecord.full_transcript || '-' }}</pre>
          </div>

          <!-- 五步卡片 -->
          <DebugStepCards
            :steps="execution?.steps || []"
            :current-code="currentBusinessCode"
            @select="currentBusinessCode = $event"
          />

          <!-- 步骤工作区 -->
          <DebugStepWorkbench
            v-if="execution"
            :business-code="currentBusinessCode"
            :steps="execution.steps"
            :config="configGroups"
          />
          <div v-else class="panel main-empty-panel">
            <a-empty description="尚未执行规则，点击「执行当前规则」后在此查看逐步转化诊断" :image-style="{ height: '56px' }" />
          </div>

          <!-- 底部 tabs：数据对比 / 标准ASR文本 -->
          <DebugCompareTabs
            :record="selectedRecord"
            :execution="execution"
            :truth="truth"
            :reference-text="referenceText"
          />
        </template>

        <!-- 未选记录空态 -->
        <div v-else class="main-empty">
          <a-empty description="从左侧选择一条历史 ASR 记录开始调试" :image-style="{ height: '64px' }" />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import {
  audioApi,
  conversionConfigApi,
  conversionPipelineApi,
  patientApi,
  resultApi,
} from '@/api/client'
import type { PipelineExecution, PipelineExecutionSummary } from '@/types/conversionPipeline'
import DebugSidebar from '@/components/ConversionPipeline/DebugSidebar.vue'
import DebugStepCards from '@/components/ConversionPipeline/DebugStepCards.vue'
import DebugStepWorkbench from '@/components/ConversionPipeline/DebugStepWorkbench.vue'
import DebugCompareTabs from '@/components/ConversionPipeline/DebugCompareTabs.vue'
import {
  mapTruthFromBUltra,
  type DebugConfigGroups,
  type SidebarRecord,
} from '@/components/ConversionPipeline/debug'

const route = useRoute()

const DEFAULT_SCENE = '卵泡监测B超'

// ========== 数据状态 ==========
const loadingRecords = ref(false)
const executing = ref(false)
const batchRunning = ref(false)
const records = ref<SidebarRecord[]>([])
const executionsBySource = ref<Map<number, PipelineExecutionSummary>>(new Map())
const selectedId = ref<number | null>(null)
const execution = ref<PipelineExecution | null>(null)
const currentBusinessCode = ref('MEDICAL_TERM')
const truth = ref<Record<string, any> | null>(null)
const referenceText = ref<string | null>(null)

// ========== 规则配置（诊断"已配置/加载规则"） ==========
const configGroups = ref<DebugConfigGroups | null>(null)
const ruleVersions = ref<any[]>([])
const ruleVersionId = ref<number | undefined>()
const loadingRuleVersion = ref(false)

const selectedRecord = computed<SidebarRecord | null>(() =>
  sidebarRecords.value.find((item) => item.id === selectedId.value) || null
)

const sidebarRecords = computed<SidebarRecord[]>(() =>
  records.value.map((item) => ({
    ...item,
    status: deriveStatus(item),
  }))
)

const statusTagColor: Record<string, string> = {
  pending: 'blue',
  review: 'orange',
  confirmed: 'green',
}
const statusTagLabel: Record<string, string> = {
  pending: '待处理',
  review: '需复核',
  confirmed: '已确认',
}

const currentRuleLabel = computed(() => {
  if (loadingRuleVersion.value) return '加载中…'
  if (!ruleVersionId.value) return '未选择规则版本'
  const found = ruleVersions.value.find((item) => item.id === ruleVersionId.value)
  return found ? `${found.version_code}${found.version_name ? ` · ${found.version_name}` : ''}` : '未选择规则版本'
})

const inputSourceLabel = computed(() => {
  if (execution.value?.input_source === 'corrected_text') return '修正文本'
  return '原始ASR（PatientAsrResult）'
})

const latestExecutionTime = computed(() => {
  if (!selectedRecord.value) return '-'
  const summary = executionsBySource.value.get(selectedRecord.value.id)
  const value = summary?.created_at || execution.value?.created_at
  return value ? String(value).replace('T', ' ').slice(0, 19) : '-'
})

const hasTruth = computed(() => {
  const data = truth.value || {}
  return Object.keys(data).some((key) => data[key] !== null && data[key] !== undefined && data[key] !== '')
})

function deriveStatus(record: SidebarRecord): SidebarRecord['status'] {
  const summary = executionsBySource.value.get(record.id)
  if (!summary) return 'pending'
  if (summary.result_level === 'AUTO_ACCEPT') return 'confirmed'
  return 'review'
}

// ========== 记录加载 ==========
async function loadRecords() {
  loadingRecords.value = true
  try {
    const examRecords: any[] = (await audioApi.getRecords()) || []
    const ids = examRecords.map((item: any) => Number(item.id)).filter(Number.isFinite)
    const recordMap = new Map(examRecords.map((item: any) => [Number(item.id), item]))
    const resultMap: Record<string, any[]> = {}
    for (let i = 0; i < ids.length; i += 100) {
      const batch = ids.slice(i, i + 100)
      const data: any = await patientApi.listAsrResultsBatch(batch)
      Object.assign(resultMap, data || {})
    }
    const flattened: SidebarRecord[] = []
    Object.entries(resultMap).forEach(([patientId, items]) => {
      const exam = recordMap.get(Number(patientId)) || {}
      ;(items || []).forEach((item: any) => {
        if (!String(item.full_transcript || '').trim()) return
        flattened.push({
          id: Number(item.id),
          patient_id: Number(patientId),
          record_id: item.record_id || exam.record_id || '',
          date: item.date || exam.date || '',
          asr_model_name: item.asr_model_name || '',
          config_hash: String(item.config_hash || ''),
          full_transcript: item.full_transcript || '',
          status: 'pending',
        })
      })
    })
    flattened.sort((a, b) => b.id - a.id)
    records.value = flattened
  } catch {
    records.value = []
  } finally {
    loadingRecords.value = false
  }
}

// ========== 执行记录（处理状态推导） ==========
async function loadExecutions() {
  try {
    const items: any = (await conversionPipelineApi.listExecutions({
      source_type: 'patient_asr_result',
      limit: 200,
    })) || []
    const map = new Map<number, PipelineExecutionSummary>()
    ;(items || []).forEach((item: PipelineExecutionSummary) => {
      if (item.source_id == null) return
      const existing = map.get(item.source_id)
      if (!existing || String(item.created_at || '') >= String(existing.created_at || '')) {
        map.set(item.source_id, item)
      }
    })
    executionsBySource.value = map
  } catch {
    executionsBySource.value = new Map()
  }
}

function upsertExecutionSummary(item: PipelineExecution) {
  const map = new Map(executionsBySource.value)
  map.set(Number(item.source_id), {
    id: item.id,
    source_type: item.source_type,
    source_id: item.source_id,
    input_source: item.input_source,
    input_text: item.input_text,
    scene: item.scene,
    rule_version_id: item.rule_version_id,
    rule_version_code: item.rule_version_code,
    config_hash: item.config_hash,
    status: item.status,
    result_level: item.result_level,
    final_text: item.final_text,
    final_fields: item.final_fields,
    final_warnings: item.final_warnings,
    final_risk_items: item.final_risk_items,
    created_at: item.created_at,
  })
  executionsBySource.value = map
}

// ========== 记录选择 ==========
async function onSelectRecord(record: SidebarRecord) {
  if (selectedId.value === record.id) return
  selectedId.value = record.id
  execution.value = null
  currentBusinessCode.value = 'MEDICAL_TERM'
  await loadRecordAux(record)
  const summary = executionsBySource.value.get(record.id)
  if (summary) {
    await loadExecutionFor(record.id, summary.id)
  }
}

async function loadRecordAux(record: SidebarRecord) {
  truth.value = null
  referenceText.value = null
  const [truthResult, referenceResult] = await Promise.all([
    resultApi.getBUltraResult(record.patient_id).catch(() => null),
    patientApi.getAsrReference(record.patient_id).catch(() => null),
  ])
  truth.value = mapTruthFromBUltra(truthResult as any) || null
  referenceText.value = String(referenceResult?.reference_text || '').trim() || null
}

async function loadExecutionFor(recordId: number, executionId: number) {
  if (selectedId.value !== recordId) return
  try {
    const data: any = await conversionPipelineApi.getExecution(executionId)
    if (selectedId.value !== recordId) return
    execution.value = data as PipelineExecution
    referenceText.value = String(execution.value.reference_text || '').trim() || referenceText.value
  } catch {
    // 执行详情加载失败不阻塞页面
  }
}

// ========== 执行 / 批量执行 ==========
async function executeCurrent() {
  const record = selectedRecord.value
  if (!record) return
  executing.value = true
  try {
    const created: any = await conversionPipelineApi.createExecution({
      source_type: 'patient_asr_result',
      source_id: record.id,
      scene: DEFAULT_SCENE,
      rule_version_id: ruleVersionId.value,
      run_mode: 'run_all',
    })
    execution.value = created as PipelineExecution
    upsertExecutionSummary(execution.value)
    referenceText.value = String(execution.value.reference_text || '').trim() || referenceText.value
    message.success(`转化完成（执行 #${created.id}）`)
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    executing.value = false
  }
}

async function onBatchRun(ids: number[]) {
  if (!ids.length) return
  batchRunning.value = true
  try {
    const result: any = await conversionPipelineApi.batchCreateExecutions({
      source_ids: ids,
      scene: DEFAULT_SCENE,
      rule_version_id: ruleVersionId.value,
    })
    const items: PipelineExecution[] = result?.items || []
    const errors: any[] = result?.errors || []
    items.forEach((item) => upsertExecutionSummary(item))
    if (selectedId.value != null) {
      const mine = items.find((item) => Number(item.source_id) === selectedId.value)
      if (mine) execution.value = mine
    }
    message.success(
      `批量执行完成：${items.length} 条成功${errors.length ? `，${errors.length} 条未执行` : ''}`
    )
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    batchRunning.value = false
  }
}

// ========== 规则版本 / 配置 ==========
async function loadRuleVersions() {
  loadingRuleVersion.value = true
  try {
    ruleVersions.value = (await conversionConfigApi.listVersions()) || []
    const published = ruleVersions.value.find((item: any) => item.status === 'published')
    ruleVersionId.value = published?.id || ruleVersions.value[0]?.id || undefined
  } catch {
    ruleVersions.value = []
  } finally {
    loadingRuleVersion.value = false
  }
}

async function loadConfig() {
  if (!ruleVersionId.value) {
    configGroups.value = { builtin: {}, lexicon: [], runtime: [] }
    try {
      const builtin: any = await conversionConfigApi.listBuiltinRules()
      configGroups.value = { builtin: builtin || {}, lexicon: [], runtime: [] }
    } catch {
      configGroups.value = { builtin: {}, lexicon: [], runtime: [] }
    }
    return
  }
  const [builtinResult, lexiconResult, runtimeResult] = await Promise.allSettled([
    conversionConfigApi.listBuiltinRules(),
    conversionConfigApi.listLexicon(ruleVersionId.value),
    conversionConfigApi.listRules(ruleVersionId.value),
  ])
  configGroups.value = {
    builtin: builtinResult.status === 'fulfilled' ? builtinResult.value : {},
    lexicon: lexiconResult.status === 'fulfilled' ? lexiconResult.value : [],
    runtime: runtimeResult.status === 'fulfilled' ? runtimeResult.value : [],
  }
}

// ========== 旧执行链接兼容（/conversion-debug/:executionId） ==========
async function restoreFromRouteParam(executionId: string) {
  try {
    const data: any = await conversionPipelineApi.getExecution(Number(executionId))
    const sourceId = Number(data?.source_id)
    const target = records.value.find((item) => item.id === sourceId)
    if (target) {
      selectedId.value = sourceId
      execution.value = data as PipelineExecution
      referenceText.value = String(execution.value.reference_text || '').trim() || null
      await loadRecordAux(target)
    }
  } catch {
    // 旧链接失效时静默忽略
  }
}

onMounted(async () => {
  await Promise.all([loadRuleVersions(), loadRecords()])
  await Promise.all([loadExecutions(), loadConfig()])
  const id = route.params.id
  if (id) await restoreFromRouteParam(String(id))
})
</script>

<style scoped>
.app {
  height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  background: #f3f5f8;
  min-width: 0;
}
.topbar {
  flex: none;
  height: 58px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 18px;
}
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
.brand-logo {
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: linear-gradient(135deg, #409eff 0%, #8b5cf6 100%);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.brand-text { min-width: 0; }
.brand-title { font-size: 16px; font-weight: 600; color: #1f2329; line-height: 1.3; }
.brand-sub {
  font-size: 12px;
  color: #8a919f;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rule-tag { margin-inline-end: 0; }

.layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 350px minmax(0, 1fr);
  overflow: hidden;
}
.main {
  min-width: 0;
  overflow-y: auto;
  padding: 14px;
  display: grid;
  gap: 12px;
  align-content: start;
}
.main-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
.panel {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
  box-shadow: 0 1px 2px rgba(31, 35, 41, 0.04);
}
.record-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.record-head-left { display: grid; gap: 6px; min-width: 0; }
.record-head-line1 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.record-title { font-size: 16px; font-weight: 700; color: #1f2329; }
.record-head-line2 { font-size: 12px; color: #5c6b7a; }
.hash-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  word-break: break-all;
  color: #1664a0;
}

.patient-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  background: #f5f6f8;
  border-radius: 8px;
  padding: 10px 12px;
}
.strip-item { min-width: 0; }
.strip-label { font-size: 11px; color: #8a919f; margin-bottom: 2px; }
.strip-value {
  font-size: 13px;
  color: #1f2329;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.raw-panel { display: grid; gap: 8px; }
.raw-title { font-size: 13px; font-weight: 600; color: #3d4757; }
.raw-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 126px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  font-size: 13px;
  color: #3d4757;
  background: #fbfcfe;
  border: 1px solid #eef2f6;
  border-radius: 6px;
  padding: 8px;
}
.main-empty-panel { display: flex; justify-content: center; padding: 28px 0; }

@media (max-width: 1280px) {
  .patient-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); row-gap: 10px; }
}
@media (max-width: 1100px) {
  .layout { grid-template-columns: 300px minmax(0, 1fr); }
}
</style>
