<template>
  <section v-if="step" class="step-workbench panel">
    <!-- 步骤标题 -->
    <div class="wb-head">
      <div class="wb-title">
        当前步骤
        <span class="wb-step-name">①{{ step.step_order / 10 }} {{ step.step_name }}</span>
        <a-tag :color="statusTagColor(step.status)">{{ statusText(step.status) }}</a-tag>
        <a-tag v-if="editedInfo.edited" color="purple">已人工修改</a-tag>
        <a-tag v-if="step.duration_ms > 0">{{ (step.duration_ms / 1000).toFixed(1) }}s</a-tag>
      </div>
      <a-space wrap>
        <a-tooltip v-if="editedInfo.edited" :title="editedInfo.tooltip">
          <a-tag color="purple" class="edit-meta-tag">修改人 {{ editedInfo.edited_by || '未知' }}</a-tag>
        </a-tooltip>
        <a-button size="small" @click="expandText = !expandText">{{ expandText ? '收起' : '展开' }}</a-button>
      </a-space>
    </div>

    <!-- 失败提示 -->
    <a-alert
      v-if="step.status === 'failed'"
      type="error"
      show-icon
      class="wb-alert"
      :message="step.error_message || '步骤执行失败'"
      description="已停止后续步骤，可修正输入后重新执行本步骤。"
    />

    <!-- dirty 提示：上游被修改 -->
    <a-alert
      v-else-if="step.status === 'dirty'"
      type="warning"
      show-icon
      class="wb-alert"
      message="上游结果已修改，当前步骤结果已失效"
      description="需要从上一个有效步骤重新运行到本步骤，不允许静默展示旧结果。"
    />

    <!-- 双栏 输入 | 输出 -->
    <div class="wb-grid">
      <div class="io-card">
        <div class="io-title">
          本步骤输入
          <a-button size="small" type="link" @click="copy(step.input_text)">复制</a-button>
        </div>
        <pre class="io-text" :class="{ expanded: expandText }">{{ step.input_text || '-' }}</pre>
        <div v-if="step.status === 'failed'" class="io-fail-rule">
          <div class="muted">执行规则：</div>
          <div v-if="(step.rule_hits || []).length" class="fail-rules">
            <a-tag v-for="(hit, idx) in step.rule_hits" :key="idx" :color="actionColor(hit.action)">{{ hit.rule_id || '-' }}</a-tag>
          </div>
          <span v-else class="muted">无</span>
        </div>
      </div>

      <div class="io-card">
        <div class="io-title">
          本步骤输出
          <a-space size="small" wrap>
            <a-button size="small" @click="copy(effectiveOutput)">复制</a-button>
            <a-button size="small" @click="showDiff = !showDiff">查看差异</a-button>
            <template v-if="!editing">
              <a-button v-if="canEdit" size="small" type="primary" ghost @click="emit('edit')">编辑</a-button>
              <a-button v-if="editedInfo.edited" size="small" @click="emit('restore-system')">恢复系统结果</a-button>
            </template>
          </a-space>
        </div>

        <!-- 编辑态 -->
        <template v-if="editing">
          <a-textarea
            v-model:value="editText"
            class="edit-textarea"
            :rows="6"
            placeholder="修改本步骤输出，保存后下游步骤将重新执行…"
          />
          <a-input
            v-model:value="editNote"
            class="edit-note"
            placeholder="修改原因（可选），如：人工确认尺寸为29×20"
            allow-clear
          />
          <div class="edit-actions">
            <a-button :loading="busy" type="primary" @click="save(true)">保存修改并从下一步继续</a-button>
            <a-button :loading="busy" @click="save(false)">仅保存修改</a-button>
            <a-button :disabled="busy" @click="emit('cancel-edit')">取消</a-button>
          </div>
        </template>

        <!-- 只读态 -->
        <template v-else>
          <pre class="io-text" :class="{ expanded: expandText }">{{ effectiveOutput || '-' }}</pre>
          <a-collapse v-if="editedInfo.edited" ghost class="system-output-collapse">
            <a-collapse-panel key="sys" header="查看系统原始结果">
              <pre class="io-text">{{ step.output_text || '-' }}</pre>
            </a-collapse-panel>
          </a-collapse>
          <div v-if="editedInfo.edit_note" class="edit-note-text">
            <span class="muted">修改原因：</span>{{ editedInfo.edit_note }}
          </div>
        </template>
      </div>
    </div>

    <!-- 差异 -->
    <a-collapse v-if="showDiff" ghost class="diff-collapse">
      <a-collapse-panel key="diff" header="输入 / 输出 差异">
        <div class="legend">
          <span class="legend-del">删除</span>
          <span class="legend-add">新增</span>
        </div>
        <pre class="diff-text"><span v-for="(seg, idx) in diffSegments" :key="idx" :class="`diff-${seg.type}`">{{ seg.text }}</span></pre>
        <div class="muted">说明：按词级比对（LCS），仅高亮内容差异，非精确逐字 diff。</div>
      </a-collapse-panel>
    </a-collapse>

    <!-- 三个摘要卡 -->
    <div class="summary-cards">
      <div class="summary-card" :class="{ clickable: ruleHits.length }" @click="ruleHits.length && emit('open-drawer', 'rules')">
        <div class="card-num" :style="{ color: ruleHits.length ? '#1677ff' : '#999' }">{{ ruleHits.length }}</div>
        <div class="card-label">命中规则</div>
      </div>
      <div class="summary-card" :class="{ clickable: fieldCount > 0 }" @click="fieldCount > 0 && emit('open-drawer', 'fields')">
        <div class="card-num" :style="{ color: fieldCount ? '#722ed1' : '#999' }">{{ fieldCount }}</div>
        <div class="card-label">字段变化</div>
      </div>
      <div class="summary-card" :class="{ clickable: warnings.length }" @click="warnings.length && emit('open-drawer', 'warnings')">
        <div class="card-num" :style="{ color: warnings.length ? '#fa8c16' : '#999' }">{{ warnings.length }}</div>
        <div class="card-label">警示</div>
      </div>
    </div>

    <!-- 底部操作 -->
    <div class="wb-actions">
      <template v-if="!editing">
        <a-button v-if="step.status === 'failed'" :loading="busy" type="primary" @click="emit('rerun')">重新执行本步骤</a-button>
        <a-button v-else-if="step.status === 'dirty'" :loading="busy" type="primary" @click="emit('rerun')">重新运行到本步骤</a-button>
        <span v-else-if="step.status === 'pending'" class="muted">尚未执行：点击步骤条中的该步骤自动执行到此步</span>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { PipelineStep, PipelineStepStatus } from '@/types/conversionPipeline'
import { simpleDiff } from './diff'

const props = defineProps<{
  step: PipelineStep
  editing: boolean
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit'): void
  (e: 'cancel-edit'): void
  (e: 'save-edit', payload: { text: string; note: string; continueNext: boolean }): void
  (e: 'restore-system'): void
  (e: 'rerun'): void
  (e: 'open-drawer', type: 'rules' | 'fields' | 'warnings'): void
}>()

const showDiff = ref(false)
const expandText = ref(false)
const editText = ref('')
const editNote = ref('')

/** 当前生效输出：人工修改优先，否则系统输出 */
const effectiveOutput = computed(() => props.step.effective_output_text || props.step.manual_output_text || props.step.output_text || '')

const editedInfo = computed(() => {
  const edited = !!(props.step.edited || props.step.manual_output_text !== null && props.step.manual_output_text !== undefined && props.step.manual_output_text !== '')
  return {
    edited,
    edited_by: props.step.edited_by || '',
    edited_at: props.step.edited_at || '',
    edit_note: props.step.edit_note || '',
    tooltip: `修改人：${props.step.edited_by || '未知'}\n修改时间：${formatTime(props.step.edited_at)}\n修改原因：${props.step.edit_note || '无'}`,
  }
})

const ruleHits = computed(() => props.step.rule_hits || [])
const warnings = computed(() => props.step.warnings || [])
const fieldCount = computed(() => {
  const fields = Object.keys(props.step.fields || {}).length
  if (fields > 0) return fields
  return countChangedFields(props.step)
})

const canEdit = computed(() => ['success', 'warning', 'manual_edited'].includes(props.step.status))

const diffSegments = computed(() => simpleDiff(props.step.input_text || '', effectiveOutput.value))

watch(() => props.step, (step) => {
  showDiff.value = false
  if (!step) return
  editText.value = step.effective_output_text || step.manual_output_text || step.output_text || ''
  editNote.value = step.edit_note || ''
}, { immediate: true })

watch(() => props.editing, (editing) => {
  if (editing) {
    editText.value = props.step.effective_output_text || props.step.manual_output_text || props.step.output_text || ''
    editNote.value = props.step.edit_note || ''
  }
})

function save(continueNext: boolean) {
  const text = editText.value
  if (!text.trim() && props.step.output_text) {
    message.warning('输出内容不能为空')
    return
  }
  emit('save-edit', { text, note: editNote.value.trim(), continueNext })
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text || '')
    message.success('已复制')
  } catch {
    message.error('复制失败，请手动复制')
  }
}

function countChangedFields(step: PipelineStep): number {
  const before = step.state_before || {}
  const after = step.state_after || {}
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))
  return keys.filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key])).length
}

function statusText(status: PipelineStepStatus) {
  return ({
    pending: '待执行',
    running: '执行中',
    success: '完成',
    warning: '需复核',
    failed: '失败',
    manual_edited: '已人工修改',
    dirty: '上游已改',
  } as Record<PipelineStepStatus, string>)[status] || status
}

function statusTagColor(status: PipelineStepStatus) {
  return ({
    pending: 'default',
    running: 'processing',
    success: 'green',
    warning: 'orange',
    failed: 'red',
    manual_edited: 'purple',
    dirty: 'gold',
  } as Record<PipelineStepStatus, string>)[status] || 'default'
}

function actionColor(action: string) {
  return ({ AUTO: 'green', CANDIDATE: 'blue', REVIEW: 'orange', BLOCK: 'red' } as any)[action] || 'default'
}

function formatTime(value?: string | null) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '-'
}
</script>

<style scoped>
.step-workbench { display: grid; gap: 12px; }
.wb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.wb-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  flex-wrap: wrap;
}
.wb-step-name { color: #1677ff; }
.edit-meta-tag { cursor: help; }
.wb-alert { margin-bottom: 0; }
.wb-grid {
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
  flex-wrap: wrap;
}
.io-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  font-size: 13px;
  background: #fafafa;
  border-radius: 4px;
  padding: 8px;
}
.io-text.expanded { max-height: none; }
.io-fail-rule { margin-top: 8px; display: grid; gap: 4px; }
.fail-rules { display: flex; gap: 4px; flex-wrap: wrap; }
.edit-textarea { font-family: inherit; font-size: 13px; line-height: 1.7; }
.edit-note { margin-top: 8px; }
.edit-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.system-output-collapse :deep(.ant-collapse-header) {
  padding: 8px 0 !important;
  font-size: 13px;
  color: #888;
}
.edit-note-text { margin-top: 6px; font-size: 13px; }
.diff-collapse :deep(.ant-collapse-header) {
  padding: 4px 0 !important;
  font-size: 13px;
}
.legend { display: inline-flex; gap: 6px; font-size: 12px; margin-bottom: 6px; }
.legend-del { color: #cf1322; background: #fff1f0; border: 1px solid #ffa39e; border-radius: 4px; padding: 0 6px; }
.legend-add { color: #389e0d; background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 4px; padding: 0 6px; }
.diff-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-family: inherit;
  line-height: 1.7;
  font-size: 13px;
}
.diff-del { color: #cf1322; background: #fff1f0; text-decoration: line-through; border-radius: 3px; padding: 0 1px; }
.diff-add { color: #389e0d; background: #f6ffed; border-radius: 3px; padding: 0 1px; }
.summary-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.summary-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 10px;
  text-align: center;
  cursor: default;
}
.summary-card.clickable { cursor: pointer; }
.summary-card.clickable:hover { border-color: #91caff; background: #fafcff; }
.card-num { font-size: 22px; font-weight: 700; line-height: 1.2; }
.card-label { font-size: 12px; color: #666; margin-top: 2px; }
.wb-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.muted { color: #888; font-size: 12px; }
@media (max-width: 1100px) {
  .wb-grid { grid-template-columns: 1fr; }
}
</style>
