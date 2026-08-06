<template>
  <section class="input-panel panel">
    <!-- 输入来源 + 规则版本 + 场景 + 主按钮 -->
    <div class="config-row">
      <a-segmented v-model:value="sourceTab" :options="sourceOptions" class="source-seg" />
      <a-tooltip :title="selectedVersionLabel" placement="top">
        <a-select
          v-model:value="ruleVersionId"
          class="version-select"
          placeholder="规则版本"
          :options="ruleVersionOptions"
          show-search
          option-filter-prop="label"
          :loading="versionLoading"
          @change="onVersionChange"
        >
          <template #option="{ label }">
            <span :title="label">{{ label }}</span>
          </template>
        </a-select>
      </a-tooltip>
      <a-select v-model:value="scene" class="scene-select" :options="sceneOptions" placeholder="业务场景" />
      <a-button
        type="primary"
        class="start-btn"
        :loading="creating"
        :disabled="!currentText.trim()"
        @click="emitStart"
      >
        开始转化
      </a-button>
    </div>

    <!-- 手动输入：大文本框 -->
    <a-textarea
      v-if="sourceTab === 'manual'"
      v-model:value="manualText"
      placeholder="粘贴一段 ASR 文本，点击「开始转化」查看逐步转化结果…"
      class="manual-textarea"
      :rows="5"
      :maxlength="100000"
    />

    <!-- 文本验证记录：复用 TextValidation 记录选择 -->
    <template v-else-if="sourceTab === 'text_validation'">
      <div class="tv-filter">
        <a-select v-model:value="tvDate" class="tv-date" :options="tvDateOptions" placeholder="日期" allow-clear />
        <a-input-search v-model:value="tvKeyword" placeholder="搜索病历号" allow-clear class="tv-search" />
        <span class="muted">共 {{ validationRows.length }} 条有验证记录的检查</span>
      </div>
      <a-table
        v-if="validationRows.length"
        size="small"
        row-key="id"
        :columns="tvColumns"
        :data-source="validationRows"
        :pagination="{ pageSize: 6, showSizeChanger: false }"
        :loading="tvLoading"
        :custom-row="tvRow"
        class="tv-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'latest_time'">
            {{ formatTime(record.latest_run?.created_at) }}
          </template>
          <template v-else-if="column.key === 'source'">
            <a-tag v-if="runsByRecord[String(record.id)]?.some((r: any) => r.raw_asr_text)">原始ASR</a-tag>
            <a-tag v-if="runsByRecord[String(record.id)]?.some((r: any) => r.corrected_text)" color="blue">修正ASR</a-tag>
          </template>
        </template>
      </a-table>
      <a-empty v-else-if="!tvLoading" description="暂无文本验证记录，请先到「文本验证」页面生成" :image-style="{ height: '48px' }" />
      <a-spin v-else />

      <div v-if="selectedRecord" class="tv-selected">
        <a-space wrap>
          <a-tag color="blue">{{ selectedRecord.record_id }}</a-tag>
          <a-tag>{{ selectedRecord.date }}</a-tag>
          <a-tag>{{ selectedRecord.segs?.length || 0 }} 段录音</a-tag>
          <a-segmented
            v-model:value="tvTextSource"
            size="small"
            :options="textSourceOptions"
            @change="onTextSourceChange"
          />
        </a-space>
        <pre class="tv-text">{{ tvPreviewText || '-' }}</pre>
        <a-collapse ghost class="tv-audio">
          <a-collapse-panel key="audio" header="回听录音">
            <AudioPlayer v-if="selectedRecord.segs?.length" :segs="selectedRecord.segs" />
            <span v-else class="muted">该记录没有录音分段</span>
          </a-collapse-panel>
        </a-collapse>
      </div>
    </template>

    <!-- 最近调试：最近 10 条执行记录 -->
    <template v-else>
      <div class="tv-filter">
        <span class="muted">最近 {{ recentExecutions.length }} 条调试记录，点击直接恢复</span>
        <a-button size="small" :loading="recentLoading" @click="loadRecent">刷新</a-button>
      </div>
      <a-table
        v-if="recentExecutions.length"
        size="small"
        row-key="id"
        :columns="recentColumns"
        :data-source="recentExecutions"
        :pagination="false"
        :loading="recentLoading"
        :custom-row="recentRow"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'created_at'">
            {{ formatTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'result_level'">
            <a-tag v-if="record.result_level" :color="levelColor[record.result_level] || 'default'">{{ levelLabel[record.result_level] || record.result_level }}</a-tag>
            <span v-else>-</span>
          </template>
        </template>
      </a-table>
      <div v-else-if="recentError" class="recent-error">
        <a-alert type="warning" show-icon message="最近调试接口暂不可用" :description="recentError" />
      </div>
      <a-empty v-else-if="!recentLoading" description="暂无调试记录" :image-style="{ height: '48px' }" />
      <a-spin v-else />
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { audioApi, conversionConfigApi, conversionPipelineApi, textValidationApi } from '@/api/client'
import type { PipelineExecutionSummary } from '@/types/conversionPipeline'
import AudioPlayer from '@/components/AudioPlayer/index.vue'

const props = defineProps<{
  creating: boolean
}>()

const emit = defineEmits<{
  (e: 'start', payload: {
    source_type: 'manual' | 'text_validation_run'
    source_id?: number
    input_source: 'manual' | 'raw_asr_text' | 'corrected_text'
    text: string
    scene: string
    rule_version_id?: number
  }): void
  (e: 'restore', executionId: number): void
}>()

const sourceOptions = [
  { label: '手动输入', value: 'manual' },
  { label: '文本验证记录', value: 'text_validation' },
  { label: '最近调试', value: 'recent' },
]
const textSourceOptions = [
  { label: '原始 ASR', value: 'raw_asr_text' },
  { label: '修正 ASR', value: 'corrected_text' },
]
const sceneOptions = [
  { label: '卵泡监测B超', value: '卵泡监测B超' },
  { label: '经腹超声', value: '经腹超声' },
  { label: '阴道超声', value: '阴道超声' },
  { label: '其他', value: '其他' },
]

const sourceTab = ref<'manual' | 'text_validation' | 'recent'>('manual')
const manualText = ref('')
const ruleVersionId = ref<number | undefined>()
const scene = ref('卵泡监测B超')
const ruleVersions = ref<any[]>([])
const versionLoading = ref(false)

const tvDate = ref<string | undefined>()
const tvKeyword = ref('')
const tvLoading = ref(false)
const records = ref<any[]>([])
const runsByRecord = ref<Record<string, any[]>>({})
const selectedRecord = ref<any | null>(null)
const tvTextSource = ref<'raw_asr_text' | 'corrected_text'>('corrected_text')

const recentExecutions = ref<PipelineExecutionSummary[]>([])
const recentLoading = ref(false)
const recentError = ref('')

const sourceLabel: Record<string, string> = {
  manual: '手动输入',
  raw_asr_text: '原始 ASR',
  corrected_text: '修正 ASR',
}
const levelLabel: Record<string, string> = {
  AUTO_ACCEPT: '自动接受',
  REVIEW_REQUIRED: '需人工复核',
  MANUAL_AUDIO_REVIEW: '需回听',
}
const levelColor: Record<string, string> = {
  AUTO_ACCEPT: 'green',
  REVIEW_REQUIRED: 'orange',
  MANUAL_AUDIO_REVIEW: 'red',
}

const ruleVersionOptions = computed(() => ruleVersions.value.map((item: any) => ({
  value: item.id,
  label: `${item.version_code} · ${item.version_name || item.version_code} · ${statusText(item.status)}`,
})))
const selectedVersionLabel = computed(() => {
  const found = ruleVersions.value.find((item: any) => item.id === ruleVersionId.value)
  return found ? `${found.version_code} · ${found.version_name || found.version_code} · ${statusText(found.status)}` : ''
})

const tvDateOptions = computed(() => {
  const set = new Set<string>()
  validationRows.value.forEach((row) => { if (row.date) set.add(String(row.date)) })
  return Array.from(set).sort().reverse().map((date) => ({ label: date, value: date }))
})

const validationRows = computed(() => {
  const q = tvKeyword.value.trim().toLowerCase()
  return records.value
    .filter((record) => {
      const runs = runsByRecord.value[String(record.id)] || []
      if (!runs.length) return false
      if (tvDate.value && String(record.date) !== tvDate.value) return false
      if (q && !String(record.record_id || '').toLowerCase().includes(q)) return false
      return true
    })
    .map((record) => {
      const runs = runsByRecord.value[String(record.id)] || []
      return { ...record, latest_run: runs[0] || null }
    })
})

const selectedRun = computed(() => {
  if (!selectedRecord.value) return null
  const runs = runsByRecord.value[String(selectedRecord.value.id)] || []
  return runs[0] || null
})

const tvPreviewText = computed(() => {
  const run = selectedRun.value
  if (!run) return ''
  return tvTextSource.value === 'raw_asr_text' ? run.raw_asr_text || '' : run.corrected_text || ''
})

/** 当前将提交转化的文本（创建时使用） */
const currentText = computed(() => {
  if (sourceTab.value === 'manual') return manualText.value
  if (sourceTab.value === 'text_validation') return tvPreviewText.value
  return ''
})

const tvColumns = [
  { title: '病历号', dataIndex: 'record_id', key: 'record_id', width: 120 },
  { title: '日期', dataIndex: 'date', key: 'date', width: 110 },
  { title: '最新验证时间', key: 'latest_time', width: 140 },
  { title: '来源', key: 'source' },
]

const recentColumns = [
  { title: '时间', key: 'created_at', width: 150 },
  { title: '来源', key: 'source', width: 120, customRender: ({ record }: any) => sourceLabel[record.input_source] || record.input_source || '-' },
  { title: '规则版本', dataIndex: 'rule_version_code', key: 'rule_version_code', width: 140 },
  { title: '结果等级', key: 'result_level', width: 120 },
]

function tvRow(record: any) {
  return {
    onClick: () => selectValidationRecord(record),
    class: record.id === selectedRecord.value?.id ? 'selected-row' : '',
  }
}

function recentRow(record: any) {
  return { onClick: () => emit('restore', record.id) }
}

function selectValidationRecord(record: any) {
  selectedRecord.value = record
  const runs = runsByRecord.value[String(record.id)] || []
  const first = runs[0]
  if (!first) return
  tvTextSource.value = first.corrected_text ? 'corrected_text' : 'raw_asr_text'
}

function onTextSourceChange(value: string | number) {
  tvTextSource.value = value as 'raw_asr_text' | 'corrected_text'
}

function onVersionChange() { /* 规则版本随开始转化提交 */ }

function statusText(status: string) {
  return ({ draft: '草稿', testing: '测试中', published: '已发布', rolled_back: '已回滚' } as any)[status] || status
}

function formatTime(value: string | null | undefined) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : '-'
}

function emitStart() {
  const text = currentText.value.trim()
  if (!text) {
    message.warning('请先输入或选择要转化的文本')
    return
  }
  if (sourceTab.value === 'text_validation' && !selectedRun.value) {
    message.warning('请先选择一条文本验证记录')
    return
  }
  const payload = sourceTab.value === 'manual'
    ? { source_type: 'manual' as const, source_id: undefined, input_source: 'manual' as const, text }
    : {
        source_type: 'text_validation_run' as const,
        source_id: selectedRun.value?.id,
        input_source: tvTextSource.value as 'raw_asr_text' | 'corrected_text',
        text,
      }
  emit('start', { ...payload, scene: scene.value, rule_version_id: ruleVersionId.value })
}

async function loadRuleVersions() {
  versionLoading.value = true
  try {
    ruleVersions.value = (await conversionConfigApi.listVersions()) || []
    const published = ruleVersions.value.find((item: any) => item.status === 'published')
    if (!ruleVersionId.value) ruleVersionId.value = published?.id || ruleVersions.value[0]?.id
  } catch { /* 版本列表加载失败不阻塞页面 */ } finally {
    versionLoading.value = false
  }
}

async function loadValidationRecords() {
  tvLoading.value = true
  try {
    const [recordData, runData]: any[] = await Promise.all([
      audioApi.getRecords(),
      textValidationApi.listRuns({ limit: 500 }).catch(() => []),
    ])
    records.value = recordData || []
    runsByRecord.value = {}
    ;(runData || []).forEach((run: any) => {
      const key = String(run.exam_record_id)
      if (!runsByRecord.value[key]) runsByRecord.value[key] = []
      const text = run.raw_asr_text || run.corrected_text
      if (text) runsByRecord.value[key].push(run)
    })
    // 每条记录按最新优先排序
    Object.values(runsByRecord.value).forEach((runs) => runs.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))))
    if (!selectedRecord.value && validationRows.value.length) selectValidationRecord(validationRows.value[0])
  } catch { /* 记录加载失败不阻塞 */ } finally {
    tvLoading.value = false
  }
}

async function loadRecent() {
  recentLoading.value = true
  recentError.value = ''
  try {
    const data: any = await conversionPipelineApi.listExecutions({ limit: 10 })
    recentExecutions.value = data || []
  } catch (error: any) {
    recentExecutions.value = []
    recentError.value = error?.response?.status === 404
      ? 'GET /api/conversion-pipeline/executions 未注册（后端版本未更新），请先更新后端。'
      : 'GET /api/conversion-pipeline/executions 请求失败，请检查后端服务。'
  } finally {
    recentLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadRuleVersions(), loadValidationRecords(), loadRecent()])
})
</script>

<style scoped>
.input-panel {
  display: grid;
  gap: 10px;
}
.config-row {
  display: grid;
  grid-template-columns: auto minmax(220px, 320px) 160px auto;
  gap: 8px;
  align-items: center;
}
.source-seg { min-width: 0; }
.manual-textarea {
  font-family: inherit;
  line-height: 1.7;
  font-size: 13px;
}
.tv-filter {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tv-date { width: 130px; }
.tv-search { width: 220px; }
.tv-table { margin-top: 4px; }
.tv-selected {
  border: 1px dashed #d9d9d9;
  border-radius: 6px;
  padding: 8px 10px;
  display: grid;
  gap: 8px;
  margin-top: 8px;
}
.tv-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 140px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.6;
  font-size: 13px;
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
}
.tv-audio :deep(.ant-collapse-header) {
  padding: 4px 0 !important;
  font-size: 13px;
  color: #1677ff;
}
.recent-error { margin-top: 4px; }
.muted { color: #888; font-size: 12px; }
@media (max-width: 1100px) {
  .config-row { grid-template-columns: 1fr; }
}
</style>
