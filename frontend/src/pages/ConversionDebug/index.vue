<template>
  <div class="conversion-debug-page">
    <!-- 页面头：标题 + 状态 + 更多菜单 -->
    <div class="page-head">
      <div class="head-left">
        <h2>ASR 转化调试</h2>
        <div class="muted">查看一段文本经过各处理步骤后的变化，可修改中间结果后继续执行</div>
      </div>
      <a-space>
        <a-tag v-if="pageStatus" :color="statusTagColor">{{ pageStatusLabel }}</a-tag>
        <a-dropdown>
          <a-button :disabled="!execution">
            <MoreOutlined /> 更多
          </a-button>
          <template #overlay>
            <a-menu @click="onMoreMenu">
              <a-menu-item key="info" :disabled="!execution">查看执行信息</a-menu-item>
              <a-menu-item key="rerun" :disabled="!execution">切换规则版本并重新运行</a-menu-item>
              <a-menu-item key="history-compare" :disabled="!execution">与历史版本对比</a-menu-item>
              <a-menu-item key="copy-link" :disabled="!execution">复制执行链接</a-menu-item>
              <a-menu-item key="export" :disabled="!execution">导出调试数据</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </a-space>
    </div>

    <!-- 顶部输入区 -->
    <InputPanel :creating="creating" @start="onStart" @restore="restoreExecution" />

    <!-- 创建失败：主区域完整错误信息（实施说明 §13） -->
    <section v-if="createError" class="panel create-error-panel">
      <div class="ce-title">
        <a-tag color="red">创建失败</a-tag>
      </div>
      <pre class="ce-request">{{ createError.method }} {{ createError.url }}</pre>
      <div class="ce-detail">
        <span class="muted">状态：</span>
        <a-tag color="red">{{ createError.status || '-' }} {{ createError.detail }}</a-tag>
      </div>
      <a-alert
        type="info"
        show-icon
        class="ce-hint"
        message="可能原因：后端版本未更新或Nginx代理端口不一致"
        description="请确认后端已包含 /api/conversion-pipeline/executions 路由，且 Nginx 代理端口与后端监听端口一致（统一 8000）。"
      />
      <a-space>
        <a-button type="primary" :loading="creating" @click="retryStart">重新尝试</a-button>
        <a-button @click="copyCreateError">复制错误信息</a-button>
      </a-space>
    </section>

    <a-spin v-if="loading" class="page-spin" />

    <!-- 主工作区 -->
    <template v-if="execution && !loading">
      <!-- 切换规则版本后的"一键对比"提示 -->
      <a-alert
        v-if="showRerunCompare"
        type="success"
        show-icon
        class="rerun-compare-alert"
        message="已使用新规则版本重新运行完成"
      >
        <template #action>
          <a-button size="small" type="primary" @click="openRerunCompare">与旧版本对比</a-button>
        </template>
      </a-alert>

      <InteractiveSteps
        :steps="execution.steps"
        :current-step-code="currentStep?.step_code"
        :disabled="busy"
        @select="onSelectStep"
      />

      <StepWorkbench
        v-if="currentStep"
        :step="currentStep"
        :editing="editingStepCode === currentStep.step_code"
        :busy="busy"
        @edit="onEdit"
        @cancel-edit="onCancelEdit"
        @save-edit="onSaveEdit"
        @restore-system="onRestoreSystem"
        @rerun="onRerunStep"
        @open-drawer="openDrawer"
      />

      <FinalResultTabs
        :execution="execution"
        :history="history"
        :busy="historyLoading"
        @view="viewHistoryItem"
        @compare="openHistoryCompare"
      />
    </template>

    <!-- 规则/警示/字段 抽屉 -->
    <RuleHitDrawer
      :open="drawerOpen"
      :type="drawerType"
      :records="drawerRecords"
      :rule-version-id="execution?.rule_version_id"
      :rule-version-code="execution?.rule_version_code"
      :version-status="drawerVersionStatus"
      :step-name="currentStep?.step_name"
      @close="drawerOpen = false"
    />

    <!-- 执行历史 / 对比抽屉 -->
    <ExecutionHistoryDrawer
      :open="historyDrawerOpen"
      :executions="history"
      :current-execution-id="execution?.id"
      :initial-compare-right-id="historyDrawerRightId"
      @close="onHistoryDrawerClose"
      @view="viewHistoryItem"
    />

    <!-- 查看执行信息 -->
    <a-modal v-model:open="infoModalOpen" title="执行信息" :footer="null" width="640px">
      <a-descriptions v-if="execution" size="small" :column="2" bordered>
        <a-descriptions-item label="执行编号">{{ execution.id }}</a-descriptions-item>
        <a-descriptions-item label="状态">{{ execution.status }}</a-descriptions-item>
        <a-descriptions-item label="来源类型">{{ sourceTypeLabel(execution.source_type) }}</a-descriptions-item>
        <a-descriptions-item label="输入来源">{{ sourceLabel(execution.input_source) }}</a-descriptions-item>
        <a-descriptions-item label="规则版本">{{ execution.rule_version_code || '-' }}</a-descriptions-item>
        <a-descriptions-item label="场景">{{ execution.scene || '-' }}</a-descriptions-item>
        <a-descriptions-item label="结果等级">{{ resultLevelLabel(execution.result_level) }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ formatTime(execution.created_at) }}</a-descriptions-item>
        <a-descriptions-item label="配置哈希" :span="2">
          <code class="hash-text">{{ execution.config_hash || '-' }}</code>
        </a-descriptions-item>
        <a-descriptions-item v-if="execution.parent_execution_id" label="源自执行" :span="2">
          #{{ execution.parent_execution_id }}
        </a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <!-- 切换规则版本并重新运行 -->
    <a-modal
      v-model:open="rerunModalOpen"
      title="切换规则版本并重新运行"
      :confirm-loading="rerunRunning"
      @ok="doRerun"
      ok-text="使用新版本重新运行"
    >
      <p class="muted">将基于当前输入文本创建新的执行记录，不会覆盖当前历史。可在新结果中一键与旧版本对比。</p>
      <a-form layout="vertical">
        <a-form-item label="当前版本">
          <a-tag color="green">{{ execution?.rule_version_code || '-' }}</a-tag>
        </a-form-item>
        <a-form-item label="新规则版本" required>
          <a-select
            v-model:value="rerunVersionId"
            :options="ruleVersionOptions"
            placeholder="选择要切换到的规则版本"
            show-search
            option-filter-prop="label"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 一键对比（新版本 vs 旧版本） -->
    <a-modal v-model:open="compareModalOpen" title="版本结果对比" width="860px" :footer="null">
      <a-space wrap v-if="compareResult">
        <a-tag color="blue">旧版本 #{{ compareResult.left_execution_id }}</a-tag>
        <span>vs</span>
        <a-tag color="purple">新版本 #{{ compareResult.right_execution_id }}</a-tag>
        <a-tag :color="compareResult.text_changed ? 'orange' : 'green'">
          文本{{ compareResult.text_changed ? '有' : '无' }}变化
        </a-tag>
        <a-tag>{{ compareResult.field_changes?.length || 0 }} 个字段变化</a-tag>
        <a-tag>{{ compareResult.new_rule_hits?.length || 0 }} 新增规则命中</a-tag>
        <a-tag>{{ compareResult.removed_rule_hits?.length || 0 }} 移除规则命中</a-tag>
      </a-space>
      <a-table
        v-if="compareResult?.field_changes?.length"
        size="small"
        row-key="fck"
        :columns="compareFieldColumns"
        :data-source="compareFieldRows"
        :pagination="false"
        class="compare-table"
      />
      <div v-if="compareResult?.new_rule_hits?.length" class="compare-list">
        <span class="muted">新增规则命中：</span>
        <a-tag v-for="code in compareResult.new_rule_hits" :key="`n-${code}`" color="orange">{{ code }}</a-tag>
      </div>
      <div v-if="compareResult?.removed_rule_hits?.length" class="compare-list">
        <span class="muted">移除规则命中：</span>
        <a-tag v-for="code in compareResult.removed_rule_hits" :key="`r-${code}`">{{ code }}</a-tag>
      </div>
      <div v-if="compareResult?.new_warnings?.length" class="compare-list">
        <span class="muted">新增警示：</span>
        <a-tag v-for="code in compareResult.new_warnings" :key="`nw-${code}`" color="red">{{ code }}</a-tag>
      </div>
      <div v-if="compareResult?.removed_warnings?.length" class="compare-list">
        <span class="muted">移除警示：</span>
        <a-tag v-for="code in compareResult.removed_warnings" :key="`rw-${code}`">{{ code }}</a-tag>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { MoreOutlined } from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { conversionConfigApi, conversionPipelineApi } from '@/api/client'
import type {
  PipelineCompareResult,
  PipelineExecution,
  PipelineExecutionSummary,
  PipelineStep,
} from '@/types/conversionPipeline'
import InputPanel from '@/components/ConversionPipeline/InputPanel.vue'
import InteractiveSteps from '@/components/ConversionPipeline/InteractiveSteps.vue'
import StepWorkbench from '@/components/ConversionPipeline/StepWorkbench.vue'
import RuleHitDrawer from '@/components/ConversionPipeline/RuleHitDrawer.vue'
import FinalResultTabs from '@/components/ConversionPipeline/FinalResultTabs.vue'
import ExecutionHistoryDrawer from '@/components/ConversionPipeline/ExecutionHistoryDrawer.vue'

const route = useRoute()
const router = useRouter()

// ========== 基础状态 ==========
const loading = ref(false)
const creating = ref(false)
const running = ref(false)
const saving = ref(false)
const execution = ref<PipelineExecution | null>(null)
const currentStep = ref<PipelineStep | null>(null)
const editingStepCode = ref<string | null>(null)

const busy = computed(() => creating.value || running.value || saving.value)

interface CreateErrorInfo {
  method: string
  url: string
  status?: number
  detail: string
}
const createError = ref<CreateErrorInfo | null>(null)
const lastStartPayload = ref<Record<string, any> | null>(null)

// ========== 规则版本（重跑 / 抽屉） ==========
const ruleVersions = ref<any[]>([])
const rerunVersionId = ref<number | undefined>()
const rerunModalOpen = ref(false)
const rerunRunning = ref(false)
const lastRerunLeftId = ref<number | null>(null)

const ruleVersionOptions = computed(() => ruleVersions.value.map((item: any) => ({
  value: item.id,
  label: `${item.version_code} · ${item.version_name || item.version_code} · ${statusText(item.status)}`,
})))

// ========== 抽屉 ==========
const drawerOpen = ref(false)
const drawerType = ref<'rules' | 'fields' | 'warnings'>('rules')
const drawerRecords = ref<Record<string, any>[]>([])
const drawerVersionStatus = computed(() => {
  if (!execution.value?.rule_version_id) return ''
  const version = ruleVersions.value.find((item: any) => item.id === execution.value?.rule_version_id)
  return version?.status || ''
})

// ========== 历史 ==========
const history = ref<PipelineExecutionSummary[]>([])
const historyLoading = ref(false)
const historyDrawerOpen = ref(false)
const historyDrawerRightId = ref<number | null>(null)

// ========== 执行信息 / 对比 ==========
const infoModalOpen = ref(false)
const compareModalOpen = ref(false)
const compareResult = ref<PipelineCompareResult | null>(null)

const showRerunCompare = computed(() => !!lastRerunLeftId.value && lastRerunLeftId.value !== execution.value?.id)

const compareFieldColumns = [
  { title: '字段', dataIndex: 'field_code', key: 'field_code', width: 180 },
  { title: '左（旧版本）', dataIndex: 'left_value', key: 'left_value' },
  { title: '右（新版本）', dataIndex: 'right_value', key: 'right_value' },
]
const compareFieldRows = computed(() => (compareResult.value?.field_changes || []).map((item, idx) => ({ ...item, fck: `fc-${idx}` })))

// ========== 页面状态（实施说明 §13） ==========
const pageStatus = computed<'idle' | 'creating' | 'running' | 'success' | 'warning' | 'failed' | 'editing' | 'dirty'>(() => {
  if (createError.value) return 'failed'
  if (!execution.value) return 'idle'
  if (creating.value) return 'creating'
  if (running.value) return 'running'
  if (editingStepCode.value) return 'editing'
  if ((execution.value.steps || []).some((step) => step.status === 'dirty')) return 'dirty'
  if (execution.value.status === 'failed') return 'failed'
  if (execution.value.result_level === 'MANUAL_AUDIO_REVIEW' || execution.value.result_level === 'REVIEW_REQUIRED') return 'warning'
  return 'success'
})

const statusTagColor = computed(() => ({
  idle: 'default',
  creating: 'processing',
  running: 'processing',
  success: 'green',
  warning: 'orange',
  failed: 'red',
  editing: 'purple',
  dirty: 'gold',
}[pageStatus.value] || 'default'))

const statusLabelMap: Record<string, string> = {
  idle: '待开始',
  creating: '创建中',
  running: '执行中',
  success: '已完成',
  warning: '需复核',
  failed: '失败',
  editing: '编辑中',
  dirty: '有待重跑',
}
const pageStatusLabel = computed(() => statusLabelMap[pageStatus.value] || pageStatus.value)

// ========== 执行数据合并 ==========
function applyExecution(data: PipelineExecution, opts: { keepStep?: boolean } = {}) {
  execution.value = data
  const steps = data.steps || []
  if (opts.keepStep) {
    const keepCode = currentStep.value?.step_code
    const found = steps.find((step) => step.step_code === keepCode)
    currentStep.value = found || steps[0] || null
  } else {
    currentStep.value = steps[0] || null
  }
}

/** 将 PATCH 步骤输出返回的 step 与 invalidated 步骤合并进执行 */
function mergePatchedStep(stepCode: string, patchedStep: PipelineStep, invalidatedCodes: string[]) {
  if (!execution.value) return
  const steps = (execution.value.steps || []).map((step) => {
    if (step.step_code === stepCode) {
      // 信任后端返回的步骤状态（编辑→manual_edited；恢复→success），缺失时按人工修改处理
      const status: PipelineStep['status'] = patchedStep.status && patchedStep.status !== 'pending' ? patchedStep.status : 'manual_edited'
      return { ...step, ...patchedStep, status }
    }
    if (invalidatedCodes.includes(step.step_code)) {
      return { ...step, status: 'dirty' as const }
    }
    return step
  })
  execution.value = { ...execution.value, steps }
  currentStep.value = steps.find((step) => step.step_code === stepCode) || currentStep.value
}

/** 本地临时把目标步骤及之后的 pending 步骤标记为 running（等待后端结果时给出反馈） */
function markRunningUntil(targetCode: string) {
  if (!execution.value) return
  const target = (execution.value.steps || []).find((step) => step.step_code === targetCode)
  if (!target) return
  const steps = (execution.value.steps || []).map((step) => (
    step.step_order >= target.step_order && step.status === 'pending' ? { ...step, status: 'running' as const } : step
  ))
  execution.value = { ...execution.value, steps }
}

// ========== 顶部输入区 ==========
async function onStart(payload: Record<string, any>) {
  creating.value = true
  createError.value = null
  lastStartPayload.value = payload
  try {
    const created: any = await conversionPipelineApi.createExecution({
      ...payload,
      run_mode: 'run_all',
    })
    applyExecution(created as PipelineExecution)
    message.success(`转化完成（执行 #${created.id}）`)
    router.replace(`/conversion-debug/${created.id}`)
    loadHistory()
  } catch (error: any) {
    createError.value = buildErrorInfo(error)
  } finally {
    creating.value = false
  }
}

function retryStart() {
  if (lastStartPayload.value) onStart(lastStartPayload.value)
}

function buildErrorInfo(error: any): CreateErrorInfo {
  const method = String(error?.config?.method || 'POST').toUpperCase()
  const url = `/api${error?.config?.url || '/conversion-pipeline/executions'}`
  const status = error?.response?.status
  const detail = error?.response?.data?.detail || error?.message || '请求失败'
  return { method, url, status, detail }
}

async function copyCreateError() {
  if (!createError.value) return
  const text = `${createError.value.method} ${createError.value.url}\n${createError.value.status || ''} ${createError.value.detail}\n可能原因：后端版本未更新或Nginx代理端口不一致`
  try {
    await navigator.clipboard.writeText(text)
    message.success('已复制错误信息')
  } catch {
    message.error('复制失败，请手动复制')
  }
}

// ========== 恢复执行 ==========
async function restoreExecution(id: number) {
  if (execution.value?.id === id && execution.value.steps?.length) {
    router.replace(`/conversion-debug/${id}`)
    return
  }
  loading.value = true
  try {
    const data: any = await conversionPipelineApi.getExecution(id)
    applyExecution(data as PipelineExecution)
    createError.value = null
    router.replace(`/conversion-debug/${id}`)
    loadHistory()
  } catch {
    execution.value = null
    currentStep.value = null
  } finally {
    loading.value = false
  }
}

// ========== 步骤条交互 ==========
async function runToStep(targetCode: string) {
  if (!execution.value) return
  running.value = true
  markRunningUntil(targetCode)
  try {
    const updated: any = await conversionPipelineApi.runToStep(execution.value.id, targetCode)
    applyExecution(updated as PipelineExecution)
    // 执行完成后停留在目标步骤（实施说明 §7.2 / TC-FE-002）
    const target = (updated.steps || []).find((step: PipelineStep) => step.step_code === targetCode)
    if (target) currentStep.value = target
    message.success(`已执行到「${target?.step_name || targetCode}」`)
    loadHistory()
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    running.value = false
  }
}

function onSelectStep(step: PipelineStep) {
  if (!execution.value) return
  const real = (execution.value.steps || []).find((item) => item.step_code === step.step_code)
  // 尚无步骤记录（create_only 未执行过任何步骤）：直接执行到该步骤
  if (!real) {
    runToStep(step.step_code)
    return
  }
  // 已完成 / 失败 / 进行中：仅切换详情，不重新执行
  if (['success', 'warning', 'manual_edited', 'failed', 'running'].includes(real.status)) {
    currentStep.value = real
    return
  }
  // dirty：上游被修改，不允许静默展示旧结果
  if (real.status === 'dirty') {
    Modal.confirm({
      title: `步骤「${real.step_name}」的上游结果已修改`,
      content: '该步骤结果已失效，需要从最近有效步骤重新执行到该步骤。是否继续？',
      okText: '重新运行到本步骤',
      cancelText: '取消',
      onOk: () => runToStep(real.step_code),
    })
    return
  }
  // pending：自动执行到该步骤
  runToStep(real.step_code)
}

// ========== 步骤编辑 / 继续 ==========
function onEdit() {
  editingStepCode.value = currentStep.value?.step_code || null
}
function onCancelEdit() {
  editingStepCode.value = null
}

async function onSaveEdit(payload: { text: string; note: string; continueNext: boolean }) {
  const step = currentStep.value
  if (!step || !execution.value) return
  saving.value = true
  try {
    const res: any = await conversionPipelineApi.patchStepOutput(execution.value.id, step.step_code, {
      manual_output_text: payload.text,
      edit_note: payload.note || undefined,
    })
    mergePatchedStep(step.step_code, res.step as PipelineStep, res.invalidated_step_codes || [])
    editingStepCode.value = null
    message.success('已保存人工修改，下游步骤已标记为待重跑')
    loadHistory()
    if (payload.continueNext) {
      await doContinue(step.step_code)
    }
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    saving.value = false
  }
}

async function onRestoreSystem() {
  const step = currentStep.value
  if (!step || !execution.value) return
  saving.value = true
  try {
    const res: any = await conversionPipelineApi.patchStepOutput(execution.value.id, step.step_code, {
      manual_output_text: step.output_text || '',
      edit_note: '恢复系统结果',
    })
    mergePatchedStep(step.step_code, res.step as PipelineStep, res.invalidated_step_codes || [])
    editingStepCode.value = null
    message.success('已恢复系统结果')
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    saving.value = false
  }
}

async function doContinue(fromStepCode: string) {
  if (!execution.value) return
  running.value = true
  try {
    const updated: any = await conversionPipelineApi.continueExecution(execution.value.id, {
      from_step_code: fromStepCode,
      run_mode: 'run_all',
    })
    applyExecution(updated as PipelineExecution, { keepStep: true })
    message.success('已从下一步继续执行完成')
    loadHistory()
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    running.value = false
  }
}

function onRerunStep() {
  const step = currentStep.value
  if (!step || !execution.value) return
  runToStep(step.step_code)
}

// ========== 抽屉 ==========
const FIELD_LABELS: Record<string, string> = {
  endometrium_thickness: '内膜厚度',
  endometrium_type: '内膜类型',
  right_ovary_size: '右卵巢大小',
  right_ovary_length: '右卵巢长',
  right_ovary_width: '右卵巢宽',
  left_ovary_size: '左卵巢大小',
  left_ovary_length: '左卵巢长',
  left_ovary_width: '左卵巢宽',
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

function openDrawer(type: 'rules' | 'fields' | 'warnings') {
  const step = currentStep.value
  if (!step) return
  drawerType.value = type
  if (type === 'rules') {
    drawerRecords.value = step.rule_hits || []
  } else if (type === 'fields') {
    drawerRecords.value = Object.entries(step.fields || {}).map(([key, value]) => ({
      key,
      label: FIELD_LABELS[key] || key,
      value: formatValue(value),
    }))
  } else {
    drawerRecords.value = (step.warnings || []).map((warning) => ({ message: warning }))
  }
  drawerOpen.value = true
}

// ========== 历史 / 对比 ==========
async function loadHistory() {
  historyLoading.value = true
  try {
    const data: any = await conversionPipelineApi.listExecutions({ limit: 10 })
    history.value = data || []
  } catch {
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

function viewHistoryItem(item: PipelineExecutionSummary) {
  restoreExecution(item.id)
}

function openHistoryCompare(executionItem: PipelineExecutionSummary) {
  historyDrawerRightId.value = executionItem.id
  historyDrawerOpen.value = true
}

function onHistoryDrawerClose() {
  historyDrawerOpen.value = false
  historyDrawerRightId.value = null
}

async function openRerunCompare() {
  if (!execution.value || !lastRerunLeftId.value) return
  compareModalOpen.value = true
  compareResult.value = null
  try {
    compareResult.value = await conversionPipelineApi.compare(lastRerunLeftId.value, execution.value.id) as PipelineCompareResult
  } catch {
    // 错误提示由 axios 拦截器统一处理
  }
}

// ========== 更多菜单 ==========
async function onMoreMenu({ key }: { key: string }) {
  switch (key) {
    case 'info':
      infoModalOpen.value = true
      break
    case 'rerun':
      rerunVersionId.value = undefined
      rerunModalOpen.value = true
      break
    case 'history-compare':
      historyDrawerRightId.value = null
      historyDrawerOpen.value = true
      break
    case 'copy-link':
      await copyExecutionLink()
      break
    case 'export':
      exportDebugData()
      break
  }
}

async function copyExecutionLink() {
  if (!execution.value) return
  const url = `${window.location.origin}${window.location.pathname.replace(/\/conversion-debug\/\d+$/, '')}/conversion-debug/${execution.value.id}`
  try {
    await navigator.clipboard.writeText(url)
    message.success('已复制执行链接')
  } catch {
    message.error('复制失败，请手动复制')
  }
}

function exportDebugData() {
  if (!execution.value) return
  const data = JSON.stringify(execution.value, null, 2)
  const blob = new Blob([data], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `conversion-debug-${execution.value.id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// ========== 切换规则版本并重新运行 ==========
async function doRerun() {
  if (!execution.value || !rerunVersionId.value) {
    message.warning('请选择新规则版本')
    return
  }
  rerunRunning.value = true
  try {
    const created: any = await conversionPipelineApi.createExecution({
      source_type: execution.value.source_type as 'manual' | 'text_validation_run' | 'conversion_preview',
      source_id: execution.value.source_id ?? undefined,
      input_source: execution.value.input_source as 'manual' | 'raw_asr_text' | 'corrected_text',
      text: execution.value.input_text,
      scene: execution.value.scene,
      rule_version_id: rerunVersionId.value,
      run_mode: 'run_all',
    })
    lastRerunLeftId.value = execution.value.id
    rerunModalOpen.value = false
    applyExecution(created as PipelineExecution)
    message.success(`已使用新版本重新运行（执行 #${created.id}）`)
    router.replace(`/conversion-debug/${created.id}`)
    loadHistory()
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    rerunRunning.value = false
  }
}

// ========== 加载 ==========
async function loadRuleVersions() {
  try {
    ruleVersions.value = (await conversionConfigApi.listVersions()) || []
  } catch { /* 版本列表加载失败不阻塞页面 */ }
}

async function loadExecution(id: number) {
  loading.value = true
  try {
    const data: any = await conversionPipelineApi.getExecution(id)
    applyExecution(data as PipelineExecution)
    createError.value = null
    loadHistory()
  } catch {
    execution.value = null
    currentStep.value = null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadRuleVersions()
  const id = route.params.id
  if (id) await loadExecution(Number(id))
  loadHistory()
})

watch(() => route.params.id, (id) => {
  if (!id) return
  if (execution.value?.id === Number(id) && execution.value.steps?.length) return
  currentStep.value = null
  loadExecution(Number(id))
})

// ========== 文案工具 ==========
function statusText(status: string) {
  return ({ draft: '草稿', testing: '测试中', published: '已发布', rolled_back: '已回滚' } as any)[status] || status
}

function formatTime(value?: string | null) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '-'
}

function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (Array.isArray(value)) return value.map((item: any) => (typeof item === 'object' ? JSON.stringify(item) : item)).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function sourceTypeLabel(sourceType: string) {
  return ({ manual: '手动输入', text_validation_run: '文本验证记录', conversion_preview: '转化预览' } as Record<string, string>)[sourceType] || sourceType || '-'
}

function sourceLabel(inputSource: string) {
  return ({ manual: '手动输入', raw_asr_text: '原始 ASR 文本', corrected_text: '修正文本' } as Record<string, string>)[inputSource] || inputSource || '-'
}

function resultLevelLabel(level?: string | null) {
  return ({ AUTO_ACCEPT: '自动接受', REVIEW_REQUIRED: '需人工复核', MANUAL_AUDIO_REVIEW: '需回听音频' } as Record<string, string>)[level || ''] || level || '-'
}
</script>

<style scoped>
.conversion-debug-page {
  padding: 16px;
  display: grid;
  gap: 12px;
  max-width: 1400px;
}
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.page-head h2 {
  margin: 0 0 4px;
}
.head-left { min-width: 0; }
.page-spin {
  display: block;
  padding: 60px 0;
}
.create-error-panel {
  display: grid;
  gap: 8px;
}
.ce-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; }
.ce-request {
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  background: #fff1f0;
  border: 1px solid #ffa39e;
  border-radius: 4px;
  padding: 8px 10px;
  word-break: break-all;
}
.ce-detail { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ce-hint { margin-bottom: 4px; }
.rerun-compare-alert { margin-top: 4px; }
.compare-table { margin-top: 10px; }
.compare-list {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.hash-text {
  font-size: 12px;
  word-break: break-all;
}
.muted { color: #888; font-size: 12px; }
</style>
