<template>
  <div class="conversion-debug-page">
    <!-- 顶部：新建执行 -->
    <section class="panel create-panel">
      <div class="panel-title">新建执行</div>
      <div class="create-row">
        <a-textarea
          v-model:value="createForm.text"
          placeholder="粘贴 ASR 原文或修正文本，创建流水线执行"
          :rows="2"
          class="create-text"
        />
        <a-input v-model:value="createForm.scene" placeholder="业务场景" class="create-scene" />
        <a-select
          v-model:value="createForm.rule_version_id"
          class="create-version"
          placeholder="规则版本"
          :options="ruleVersionOptions"
          allow-clear
          show-search
          option-filter-prop="label"
        />
        <a-button
          type="primary"
          :loading="creating"
          :disabled="!createForm.text.trim()"
          @click="createExecution"
        >
          创建执行
        </a-button>
      </div>
    </section>

    <a-empty v-if="!execution && !loading" description="请创建执行，或在地址栏输入执行编号 /conversion-debug/:id" />

    <template v-if="execution">
      <!-- 执行信息 -->
      <section class="panel exec-panel">
        <div class="exec-info">
          <span class="exec-title">执行 #{{ execution.id }}</span>
          <a-tag>{{ inputSourceText }}</a-tag>
          <a-tag>规则版本 {{ execution.rule_version_code || '-' }}</a-tag>
          <a-tag>配置哈希 {{ shortHash }}</a-tag>
          <a-tag v-if="execution.parent_execution_id">源自执行 #{{ execution.parent_execution_id }}</a-tag>
        </div>
        <a-space wrap>
          <a-button :loading="runningAll" :disabled="!canRunAll" @click="runAll">运行全部</a-button>
          <a-button :disabled="!currentStep" @click="openForkModal">基于新规则重跑</a-button>
          <a-button @click="openCompareModal">对比执行</a-button>
          <a-button
            v-if="execution.source_type === 'text_validation_run'"
            size="small"
            :loading="audioLoading"
            @click="loadAudio"
          >
            回听录音
          </a-button>
        </a-space>
        <div v-if="audioSegs.length" class="audio-box">
          <AudioPlayer :segs="audioSegs" />
        </div>
      </section>

      <!-- 步骤条 -->
      <section class="panel">
        <PipelineSteps
          :steps="execution.steps || []"
          :current-step-order="currentStep?.step_order"
          @select="selectStep"
        />
      </section>

      <!-- 步骤详情 -->
      <section v-if="currentStep" class="panel">
        <div class="step-detail-grid">
          <div class="step-detail-left">
            <div class="panel-title">步骤输入 / 输出 / 差异</div>
            <StepInputOutput :step="currentStep" />
          </div>
          <div class="step-detail-right">
            <div class="sub-block">
              <div class="panel-title">命中规则（{{ (currentStep.rule_hits || []).length }}）</div>
              <StepRuleList
                :step="currentStep"
                :rule-version-id="execution.rule_version_id"
                :rule-version-code="execution.rule_version_code"
              />
            </div>
            <div class="sub-block">
              <div class="panel-title">状态机变化</div>
              <StateTrace :step="currentStep" />
            </div>
          </div>
        </div>
      </section>

      <!-- 执行摘要 -->
      <section class="panel">
        <ExecutionSummary :execution="execution" />
      </section>
    </template>

    <!-- fork：基于新规则重跑 -->
    <a-modal v-model:open="forkModalOpen" title="基于新规则重跑（fork 到新执行，不覆盖旧执行）" @ok="doFork" :confirm-loading="forking">
      <a-form layout="vertical">
        <a-form-item label="起始步骤">
          <a-select v-model:value="forkForm.step_code" :options="stepOptions" placeholder="选择起始步骤" />
        </a-form-item>
        <a-form-item label="新规则版本">
          <a-select
            v-model:value="forkForm.rule_version_id"
            :options="ruleVersionOptions"
            placeholder="不选则沿用当前版本"
            allow-clear
            show-search
            option-filter-prop="label"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 对比执行 -->
    <a-modal v-model:open="compareModalOpen" title="对比执行" width="860px" @ok="doCompare" :confirm-loading="comparing">
      <a-row :gutter="12">
        <a-col :span="12">
          <a-form-item label="左执行编号"><a-input-number v-model:value="compareForm.left_id" class="full" :min="1" /></a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="右执行编号"><a-input-number v-model:value="compareForm.right_id" class="full" :min="1" /></a-form-item>
        </a-col>
      </a-row>
      <template v-if="compareResult">
        <a-divider orientation="left">对比结果</a-divider>
        <a-space wrap>
          <a-tag :color="compareResult.text_changed ? 'orange' : 'green'">
            文本{{ compareResult.text_changed ? '有' : '无' }}变化
          </a-tag>
          <a-tag>{{ compareResult.field_changes?.length || 0 }} 个字段变化</a-tag>
          <a-tag>{{ compareResult.new_rule_hits?.length || 0 }} 新增规则命中</a-tag>
          <a-tag>{{ compareResult.removed_rule_hits?.length || 0 }} 移除规则命中</a-tag>
        </a-space>
        <a-table
          v-if="compareResult.field_changes?.length"
          size="small"
          row-key="fck"
          :columns="compareFieldColumns"
          :data-source="compareFieldRows"
          :pagination="false"
          class="compare-table"
        />
        <div v-if="compareResult.new_rule_hits?.length" class="compare-list">
          <span class="muted">新增规则命中：</span>
          <a-tag v-for="code in compareResult.new_rule_hits" :key="`n-${code}`" color="orange">{{ code }}</a-tag>
        </div>
        <div v-if="compareResult.removed_rule_hits?.length" class="compare-list">
          <span class="muted">移除规则命中：</span>
          <a-tag v-for="code in compareResult.removed_rule_hits" :key="`r-${code}`">{{ code }}</a-tag>
        </div>
        <div v-if="compareResult.new_warnings?.length" class="compare-list">
          <span class="muted">新增警示：</span>
          <a-tag v-for="code in compareResult.new_warnings" :key="`nw-${code}`" color="red">{{ code }}</a-tag>
        </div>
        <div v-if="compareResult.removed_warnings?.length" class="compare-list">
          <span class="muted">移除警示：</span>
          <a-tag v-for="code in compareResult.removed_warnings" :key="`rw-${code}`">{{ code }}</a-tag>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import {
  audioApi,
  conversionConfigApi,
  conversionPipelineApi,
  textValidationApi,
} from '@/api/client'
import type {
  PipelineCompareResult,
  PipelineExecution,
  PipelineStep,
} from '@/types/conversionPipeline'
import AudioPlayer from '@/components/AudioPlayer/index.vue'
import PipelineSteps from '@/components/ConversionPipeline/PipelineSteps.vue'
import StepInputOutput from '@/components/ConversionPipeline/StepInputOutput.vue'
import StepRuleList from '@/components/ConversionPipeline/StepRuleList.vue'
import StateTrace from '@/components/ConversionPipeline/StateTrace.vue'
import ExecutionSummary from '@/components/ConversionPipeline/ExecutionSummary.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const creating = ref(false)
const runningAll = ref(false)
const forking = ref(false)
const comparing = ref(false)
const execution = ref<PipelineExecution | null>(null)
const currentStep = ref<PipelineStep | null>(null)
const ruleVersions = ref<any[]>([])
const audioLoading = ref(false)
const audioSegs = ref<any[]>([])

const createForm = reactive({
  text: '',
  scene: '卵泡监测B超',
  rule_version_id: undefined as number | undefined,
})

const forkModalOpen = ref(false)
const forkForm = reactive({
  step_code: undefined as string | undefined,
  rule_version_id: undefined as number | undefined,
})

const compareModalOpen = ref(false)
const compareForm = reactive({
  left_id: undefined as number | undefined,
  right_id: undefined as number | undefined,
})
const compareResult = ref<PipelineCompareResult | null>(null)

const ruleVersionOptions = computed(() => ruleVersions.value.map((item) => ({
  value: item.id,
  label: `${item.version_name || item.version_code} · ${item.status}`,
})))

const stepOptions = computed(() => (execution.value?.steps || []).map((step) => ({
  value: step.step_code,
  label: `${step.step_order}. ${step.step_name}`,
})))

const inputSourceText = computed(() => {
  const source = execution.value?.input_source || ''
  const labels: Record<string, string> = {
    manual: '手动输入',
    raw_asr_text: '原始 ASR 文本',
    corrected_text: '修正文本',
  }
  return labels[source] || source || '-'
})

const shortHash = computed(() => {
  const hash = execution.value?.config_hash || ''
  return hash ? `${hash.slice(0, 10)}${hash.length > 10 ? '…' : ''}` : '-'
})

/** 存在待执行（pending/failed）步骤时才允许“运行全部” */
const canRunAll = computed(() => (execution.value?.steps || []).some((step) => step.status === 'pending' || step.status === 'failed'))

const compareFieldColumns = [
  { title: '字段', dataIndex: 'field_code', key: 'field_code', width: 180 },
  { title: '左（旧执行）', dataIndex: 'left_value', key: 'left_value' },
  { title: '右（新执行）', dataIndex: 'right_value', key: 'right_value' },
]
const compareFieldRows = computed(() => (compareResult.value?.field_changes || []).map((item, idx) => ({ ...item, fck: `fc-${idx}` })))

function selectStep(step: PipelineStep) {
  currentStep.value = step
}

async function loadExecution(id: number) {
  loading.value = true
  try {
    execution.value = await conversionPipelineApi.getExecution(id) as PipelineExecution
    const first = execution.value?.steps?.[0] || null
    currentStep.value = first && currentStep.value && currentStep.value.step_order === first.step_order
      ? currentStep.value
      : first
  } catch {
    execution.value = null
    currentStep.value = null
  } finally {
    loading.value = false
  }
}

async function createExecution() {
  const text = createForm.text.trim()
  if (!text) return
  creating.value = true
  try {
    const created: any = await conversionPipelineApi.createExecution({
      source_type: 'manual',
      input_source: 'manual',
      text,
      scene: createForm.scene,
      rule_version_id: createForm.rule_version_id,
      run_mode: 'run_all',
    })
    message.success(`已创建执行 #${created.id}`)
    router.push(`/conversion-debug/${created.id}`)
  } finally {
    creating.value = false
  }
}

async function runAll() {
  if (!execution.value) return
  runningAll.value = true
  try {
    const steps = execution.value.steps || []
    for (const step of steps) {
      if (step.status !== 'pending' && step.status !== 'failed') continue
      const updated: any = await conversionPipelineApi.runStep(execution.value.id, step.step_code)
      execution.value = updated as PipelineExecution
      currentStep.value = (updated.steps || []).find((item: PipelineStep) => item.step_order === step.step_order) || currentStep.value
    }
    message.success('执行完成')
  } catch {
    // 错误提示由 axios 拦截器统一处理
  } finally {
    runningAll.value = false
  }
}

function openForkModal() {
  if (!execution.value) return
  forkForm.step_code = currentStep.value?.step_code || execution.value.steps?.[0]?.step_code
  forkForm.rule_version_id = undefined
  forkModalOpen.value = true
}

async function doFork() {
  if (!execution.value || !forkForm.step_code) {
    message.warning('请选择起始步骤')
    return
  }
  forking.value = true
  try {
    const created: any = await conversionPipelineApi.forkFromStep(execution.value.id, {
      step_code: forkForm.step_code,
      rule_version_id: forkForm.rule_version_id,
    })
    forkModalOpen.value = false
    message.success(`已创建 fork 执行 #${created.id}`)
    router.push(`/conversion-debug/${created.id}`)
  } finally {
    forking.value = false
  }
}

function openCompareModal() {
  if (!execution.value) return
  compareForm.left_id = execution.value.id
  compareForm.right_id = undefined
  compareResult.value = null
  compareModalOpen.value = true
}

async function doCompare() {
  if (!compareForm.left_id || !compareForm.right_id) {
    message.warning('请填写左右执行编号')
    return
  }
  comparing.value = true
  try {
    compareResult.value = await conversionPipelineApi.compare(compareForm.left_id, compareForm.right_id) as PipelineCompareResult
  } finally {
    comparing.value = false
  }
}

/** 文本验证来源的执行：加载对应检查记录录音（懒加载） */
async function loadAudio() {
  if (!execution.value || execution.value.source_type !== 'text_validation_run') return
  audioLoading.value = true
  try {
    const run: any = await textValidationApi.getRun(execution.value.source_id as number)
    const records: any[] = await audioApi.getRecords()
    const record = (records || []).find((item) => item.id === run.exam_record_id)
    if (record?.segs?.length) {
      audioSegs.value = record.segs
      message.success(`已加载 ${record.record_id} 的录音分段`)
    } else {
      audioSegs.value = []
      message.info('未找到该执行的录音分段')
    }
  } catch {
    audioSegs.value = []
  } finally {
    audioLoading.value = false
  }
}

onMounted(async () => {
  try {
    ruleVersions.value = (await conversionConfigApi.listVersions()) || []
  } catch { /* 版本列表加载失败不阻塞页面 */ }
  const id = route.params.id
  if (id) await loadExecution(Number(id))
})

watch(() => route.params.id, (id) => {
  if (!id) return
  audioSegs.value = []
  currentStep.value = null
  loadExecution(Number(id))
})
</script>

<style scoped>
.conversion-debug-page {
  padding: 16px;
  display: grid;
  gap: 12px;
}
.panel {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  min-width: 0;
}
.panel-title {
  font-weight: 600;
  margin-bottom: 10px;
}
.create-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 180px 240px auto;
  gap: 8px;
}
.exec-panel {
  display: grid;
  gap: 10px;
}
.exec-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.exec-title {
  font-size: 15px;
  font-weight: 600;
}
.audio-box {
  border-top: 1px solid #f0f0f0;
  padding-top: 10px;
}
.step-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 12px;
}
.step-detail-left {
  min-width: 0;
}
.step-detail-right {
  display: grid;
  gap: 12px;
  align-content: start;
  min-width: 0;
}
.sub-block {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px;
}
.compare-table {
  margin-top: 10px;
}
.compare-list {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.full { width: 100%; }
.muted { color: #888; font-size: 12px; }
@media (max-width: 1100px) {
  .create-row { grid-template-columns: 1fr; }
  .step-detail-grid { grid-template-columns: 1fr; }
}
</style>
