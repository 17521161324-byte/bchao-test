<template>
  <a-drawer
    :open="open"
    title="执行历史与对比"
    :width="760"
    @close="close"
  >
    <!-- 对比结果 -->
    <template v-if="compareResult">
      <div class="compare-head">
        <a-space wrap>
          <a-tag color="blue">执行 #{{ leftExecution?.id }}</a-tag>
          <span>vs</span>
          <a-tag color="purple">执行 #{{ compareResult.right_execution_id }}</a-tag>
          <a-tag :color="compareResult.text_changed ? 'orange' : 'green'">
            最终文本{{ compareResult.text_changed ? '有变化' : '无变化' }}
          </a-tag>
          <a-tag>{{ compareResult.field_changes?.length || 0 }} 个字段变化</a-tag>
        </a-space>
        <a-button size="small" @click="resetCompare">返回历史列表</a-button>
      </div>
      <a-divider orientation="left">字段变化</a-divider>
      <a-table
        v-if="compareFieldRows.length"
        size="small"
        row-key="fck"
        :columns="compareFieldColumns"
        :data-source="compareFieldRows"
        :pagination="false"
      />
      <span v-else class="muted">无字段变化</span>

      <a-divider orientation="left">规则命中变化</a-divider>
      <div class="compare-tags">
        <span v-if="compareResult.new_rule_hits?.length" class="tag-line">
          <span class="muted">新增命中：</span>
          <a-tag v-for="code in compareResult.new_rule_hits" :key="`n-${code}`" color="orange">{{ code }}</a-tag>
        </span>
        <span v-if="compareResult.removed_rule_hits?.length" class="tag-line">
          <span class="muted">移除命中：</span>
          <a-tag v-for="code in compareResult.removed_rule_hits" :key="`r-${code}`">{{ code }}</a-tag>
        </span>
        <span v-if="!compareResult.new_rule_hits?.length && !compareResult.removed_rule_hits?.length" class="muted">无规则命中变化</span>
      </div>

      <a-divider orientation="left">警示变化</a-divider>
      <div class="compare-tags">
        <span v-if="compareResult.new_warnings?.length" class="tag-line">
          <span class="muted">新增警示：</span>
          <a-tag v-for="code in compareResult.new_warnings" :key="`nw-${code}`" color="red">{{ code }}</a-tag>
        </span>
        <span v-if="compareResult.removed_warnings?.length" class="tag-line">
          <span class="muted">移除警示：</span>
          <a-tag v-for="code in compareResult.removed_warnings" :key="`rw-${code}`">{{ code }}</a-tag>
        </span>
        <span v-if="!compareResult.new_warnings?.length && !compareResult.removed_warnings?.length" class="muted">无警示变化</span>
      </div>
    </template>

    <!-- 历史列表 -->
    <template v-else>
      <div class="history-tip muted">选择一条历史执行，可查看或与当前结果（#{{ currentExecutionId || '-' }}）对比</div>
      <a-table
        size="small"
        row-key="id"
        :columns="historyColumns"
        :data-source="executions"
        :pagination="{ pageSize: 8, showSizeChanger: false }"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'result_level'">
            <a-tag v-if="record.result_level" :color="levelColor(record.result_level)">{{ levelLabel(record.result_level) }}</a-tag>
            <span v-else>-</span>
          </template>
          <template v-else-if="column.key === 'manual'">
            <a-tag v-if="record.manual_edited || record.edited" color="purple">已人工修改</a-tag>
            <span v-else>-</span>
          </template>
          <template v-else-if="column.key === 'ops'">
            <a-space size="small">
              <a-button size="small" type="link" @click="emit('view', record)">查看</a-button>
              <a-button size="small" type="link" @click="startCompare(record)">与当前对比</a-button>
            </a-space>
          </template>
        </template>
      </a-table>
      <a-alert v-if="compareError" type="error" show-icon class="compare-error" :message="compareError" />
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { conversionPipelineApi } from '@/api/client'
import type { PipelineCompareResult, PipelineExecutionSummary, PipelineResultLevel } from '@/types/conversionPipeline'

const props = defineProps<{
  open: boolean
  executions: PipelineExecutionSummary[]
  currentExecutionId?: number | null
  /** 从最终结果“执行历史”tab 预设的对比目标 */
  initialCompareRightId?: number | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'view', execution: PipelineExecutionSummary): void
}>()

const loading = ref(false)
const compareResult = ref<PipelineCompareResult | null>(null)
const compareError = ref('')
const leftExecution = ref<PipelineExecutionSummary | null>(null)

const historyColumns = [
  { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 150, customRender: ({ text }: any) => formatTime(text) },
  { title: '来源', key: 'source', width: 110, customRender: ({ record }: any) => sourceLabel(record) },
  { title: '规则版本', dataIndex: 'rule_version_code', key: 'rule_version_code', width: 140 },
  { title: '结果等级', key: 'result_level', width: 110 },
  { title: '人工修改', key: 'manual', width: 100 },
  { title: '操作', key: 'ops', width: 150 },
]

const compareFieldColumns = [
  { title: '字段', dataIndex: 'field_code', key: 'field_code', width: 180 },
  { title: '左（当前）', dataIndex: 'left_value', key: 'left_value' },
  { title: '右（历史）', dataIndex: 'right_value', key: 'right_value' },
]
const compareFieldRows = computed(() => (compareResult.value?.field_changes || []).map((item, idx) => ({ ...item, fck: `fc-${idx}` })))

function sourceLabel(record: PipelineExecutionSummary) {
  return ({
    manual: '手动输入',
    raw_asr_text: '原始 ASR',
    corrected_text: '修正 ASR',
    text_validation_run: '文本验证',
  } as Record<string, string>)[record.input_source || ''] || record.input_source || '-'
}

function levelColor(level: PipelineResultLevel) {
  return ({ AUTO_ACCEPT: 'green', REVIEW_REQUIRED: 'orange', MANUAL_AUDIO_REVIEW: 'red' } as Record<PipelineResultLevel, string>)[level] || 'default'
}

function levelLabel(level: PipelineResultLevel) {
  return ({ AUTO_ACCEPT: '自动接受', REVIEW_REQUIRED: '需人工复核', MANUAL_AUDIO_REVIEW: '需回听' } as Record<PipelineResultLevel, string>)[level] || level
}

function formatTime(value?: string) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : '-'
}

function resetCompare() {
  compareResult.value = null
  compareError.value = ''
  leftExecution.value = null
}

async function startCompare(right: PipelineExecutionSummary) {
  const leftId = props.currentExecutionId
  if (!leftId) {
    compareError.value = '当前没有可对比的执行记录'
    return
  }
  if (leftId === right.id) {
    compareError.value = '不能与当前执行自身对比'
    return
  }
  loading.value = true
  compareError.value = ''
  leftExecution.value = props.executions.find((item) => item.id === leftId) || null
  try {
    compareResult.value = await conversionPipelineApi.compare(leftId, right.id) as PipelineCompareResult
  } catch (error: any) {
    compareResult.value = null
    compareError.value = error?.response?.status === 404 ? '对比接口不可用（后端版本未更新）' : '对比失败，请检查执行记录'
  } finally {
    loading.value = false
  }
}

function close() {
  resetCompare()
  emit('close')
}

watch(() => props.open, (open) => {
  if (!open) {
    resetCompare()
    return
  }
  if (props.initialCompareRightId) {
    const right = props.executions.find((item) => item.id === props.initialCompareRightId)
    if (right) startCompare(right)
  }
})
</script>

<style scoped>
.history-tip { margin-bottom: 10px; }
.compare-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.compare-tags { display: grid; gap: 8px; }
.tag-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.compare-error { margin-top: 12px; }
.muted { color: #888; font-size: 12px; }
</style>
