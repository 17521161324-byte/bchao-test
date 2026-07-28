<template>
  <div class="batch-detail">
    <a-card v-if="batch">
      <template #title>
        <a-space>
          <a-button size="small" @click="goBack">返回列表</a-button>
          <span>{{ batch.name }}</span>
          <a-tag color="blue">{{ batch.record_count }} 条记录</a-tag>
          <a-tag :color="accuracyColor(batch.average_accuracy)">平均准确率 {{ percent(batch.average_accuracy) }}</a-tag>
        </a-space>
      </template>
      <template #extra>
        <a-space>
          <a-dropdown>
            <a-button size="small">
              更多操作 <DownOutlined />
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="batch-eval" @click="batchEvaluate" :disabled="judging || calculating">
                  <a-spin v-if="judging || calculating" size="small" /> 批量评估/重算
                </a-menu-item>
                <a-menu-item key="batch-run" @click="batchRunConversion" :disabled="converting">
                  <a-spin v-if="converting" size="small" /> 批量运行转化引擎
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item key="delete" @click="confirmDeleteBatch" style="color: #ff4d4f">
                  删除批次
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </a-space>
      </template>

      <a-row :gutter="12" class="main-content">
        <!-- 左侧：检查记录列表 -->
        <a-col :span="4" class="left-sidebar">
          <a-card size="small" :body-style="{ padding: '6px' }" class="sidebar-card">
            <div class="record-list">
              <div
                v-for="rec in batch.records"
                :key="rec.id"
                class="record-item"
                :class="{ active: currentRecordId === rec.id }"
                @click="selectRecord(rec.id)"
              >
                <div class="record-id">
                  {{ rec.record_id_snapshot }}
                  <a-tag v-if="rec.status === 'failed'" color="red" class="record-status">失败</a-tag>
                </div>
                <div class="record-date">{{ rec.date_snapshot }}</div>
              </div>
              <a-empty v-if="!batch.records?.length" description="暂无记录" :image="false" />
            </div>
          </a-card>
        </a-col>

        <!-- 右侧：详情 -->
        <a-col :span="20">
          <template v-if="detail">
            <!-- 第一行：属性区 -->
            <div class="attr-row">
              <a-tag color="blue">{{ detail.record_id_snapshot }}</a-tag>
              <a-tag>{{ detail.date_snapshot }}</a-tag>
              <a-tag>{{ detail.asr_model_name || '未知 ASR' }}</a-tag>
              <a-tag>{{ detail.conversion_version }}</a-tag>
              <a-tag :color="detail.status === 'failed' ? 'red' : detail.risk_blocked ? 'red' : detail.risk_passed ? 'green' : 'orange'">
                {{ detail.status === 'failed' ? 'ASR失败' : detail.risk_blocked ? '风险阻断' : detail.risk_passed ? '风险通过' : '风险警告' }}
              </a-tag>
              <a-select v-model:value="detail.review_status" size="small" style="width: 120px" :options="reviewStatusOptions" @change="saveRecordStatus" />
            </div>

            <!-- 第二行：指标卡片 -->
            <div v-if="detail.metrics_summary" class="metrics-row">
              <a-tag color="blue">实际转化 {{ detail.metrics_summary.actual_conversion_count || 0 }}</a-tag>
              <a-tag color="green">正确 {{ detail.metrics_summary.correct_conversion_count || 0 }}</a-tag>
              <a-tag color="red">错误 {{ detail.metrics_summary.wrong_conversion_count || 0 }}</a-tag>
              <a-tag color="orange">漏转 {{ detail.metrics_summary.missed_conversion_count || 0 }}</a-tag>
              <a-tag color="purple">过度 {{ detail.metrics_summary.over_conversion_count || 0 }}</a-tag>
              <a-tag color="red">高风险 {{ detail.metrics_summary.high_risk_error_count || 0 }}</a-tag>
              <a-tag :color="accuracyColor(detail.metrics_summary.conversion_accuracy)">准确率 {{ percent(detail.metrics_summary.conversion_accuracy) }}</a-tag>
            </div>

            <!-- 第三行：操作按钮 -->
            <div class="action-row">
              <a-space>
                <a-button size="small" type="primary" @click="runConversion" :loading="converting" :disabled="detail.status === 'failed'">运行转化引擎</a-button>
                <a-button size="small" @click="autoJudge" :loading="judging" :disabled="detail.status === 'failed'">自动判定</a-button>
                <a-button size="small" @click="calculateMetrics" :loading="calculating" :disabled="detail.status === 'failed'">计算指标</a-button>
              </a-space>
            </div>

            <a-alert
              v-if="detail.status === 'failed'"
              type="error"
              show-icon
              :message="detail.error_message || '该检查记录没有可用的 ASR 转写结果'"
              style="margin-bottom: 12px"
            />

            <!-- 录音播放 -->
            <a-card v-if="currentSegs?.length" size="small" title="录音播放" class="section-card">
              <AudioPlayer :segs="currentSegs" />
            </a-card>
            <a-card v-else size="small" title="录音播放" class="section-card">
              <a-empty description="该检查记录无录音" :image="false" />
            </a-card>

            <!-- 警告 -->
            <a-alert v-if="detail.warnings" type="warning" show-icon style="margin: 12px 0">
              <template #message>
                <div style="white-space: pre-wrap; max-height: 150px; overflow: auto;">{{ detail.warnings }}</div>
              </template>
            </a-alert>

            <!-- 三栏文本 -->
            <a-row :gutter="12" class="text-columns">
              <a-col :span="8">
                <a-card size="small" title="原始 ASR">
                  <div
                    ref="rawTextRef"
                    class="text-panel selectable-text"
                    @mouseup="onRawTextSelect"
                  >{{ detail.raw_text || '暂无文本' }}</div>
                </a-card>
              </a-col>
              <a-col :span="8">
                <a-card size="small">
                  <template #title>
                    <a-space>
                      <span>转化后 ASR</span>
                      <a-button size="small" @click="editingConverted = !editingConverted">{{ editingConverted ? '预览' : '编辑' }}</a-button>
                    </a-space>
                  </template>
                  <div
                    v-if="!editingConverted"
                    ref="convertedTextRef"
                    class="text-panel selectable-text"
                    @mouseup="onConvertedTextSelect"
                  >
                    <span
                      v-for="(seg, idx) in convertedSegments"
                      :key="idx"
                      :class="getConvertedClass(seg)"
                    >{{ seg.text }}</span>
                  </div>
                  <a-textarea v-else v-model:value="detail.converted_text" :rows="14" @blur="saveConvertedText" />
                </a-card>
              </a-col>
              <a-col :span="8">
                <a-card size="small" title="专家标准 ASR">
                  <div class="text-panel">
                    <span
                      v-for="(seg, idx) in diffSegments"
                      :key="idx"
                      :class="referenceMarkClass(seg.type)"
                      :title="seg.note || ''"
                    >{{ seg.text }}</span>
                  </div>
                </a-card>
              </a-col>
            </a-row>

            <!-- 专家标记列表 -->
            <a-card v-if="detail.reference_annotations?.length" size="small" class="section-card" title="专家标记">
              <a-table
                row-key="idx"
                size="small"
                :columns="annotationColumns"
                :data-source="(detail.reference_annotations || []).map((a: any, idx: number) => ({ ...a, idx }))"
                :pagination="false"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'type'">
                    <a-tag :color="record.type === 'red' ? 'red' : record.type === 'orange' ? 'orange' : 'green'">
                      {{ annotationTypeText(record.type) }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.key === 'text'">
                    {{ (detail.reference_text || '').slice(record.start, record.end) }}
                  </template>
                </template>
              </a-table>
            </a-card>

            <!-- 转化片段 -->
            <a-card size="small" class="section-card">
              <template #title>
                <a-space>
                  <span>转化片段</span>
                  <a-tag v-if="selectedDetailId" color="orange" closable @close="selectedDetailId = null">已选中片段</a-tag>
                  <a-button size="small" type="primary" @click="openDetailModal()">新增片段</a-button>
                </a-space>
              </template>

              <!-- 选区提示 -->
              <div v-if="hasSelection" class="selection-bar">
                <a-space>
                  <span class="selection-label">当前选区：</span>
                  <a-tag v-if="selectedRawText" color="blue">原始：{{ selectedRawText.slice(0, 30) }}{{ selectedRawText.length > 30 ? '...' : '' }}</a-tag>
                  <a-tag v-if="selectedConvertedText" color="green">转化后：{{ selectedConvertedText.slice(0, 30) }}{{ selectedConvertedText.length > 30 ? '...' : '' }}</a-tag>
                  <a-button size="small" type="primary" @click="openDetailModal()">使用选区新增片段</a-button>
                  <a-button size="small" @click="clearSelection">清空选区</a-button>
                </a-space>
              </div>

              <a-table
                row-key="id"
                size="small"
                :columns="detailColumns"
                :data-source="detail.details || []"
                :pagination="false"
                :row-class-name="getRowClassName"
                @row-click="onRowClick"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'judge'">
                    <a-select
                      :value="record.manual_judgement || record.final_judgement || record.system_judgement"
                      size="small"
                      style="width: 120px"
                      :options="judgeOptions"
                      allow-clear
                      @change="(v: string) => setManualJudge(record, v)"
                    />
                  </template>
                  <template v-else-if="column.key === 'match'">
                    <template v-if="detail?.reference_text">
                      <a-tag :color="getFragmentMatchStatus(record.id)?.matchStatus === 'matched' ? 'green' : getFragmentMatchStatus(record.id)?.matchStatus === 'unmatched' ? 'red' : 'default'">
                        {{ getFragmentMatchStatus(record.id)?.matchStatus === 'matched' ? '匹配' : getFragmentMatchStatus(record.id)?.matchStatus === 'unmatched' ? '未匹配' : '待确认' }}
                      </a-tag>
                      <div v-if="getFragmentMatchStatus(record.id)?.matchNote" class="match-note">{{ getFragmentMatchStatus(record.id)?.matchNote }}</div>
                    </template>
                    <span v-else class="muted">-</span>
                  </template>
                  <template v-else-if="column.key === 'risk'">
                    <a-tag :color="record.risk_level === 'high' ? 'red' : record.risk_level === 'medium' ? 'orange' : 'default'">
                      {{ record.risk_type || record.risk_level || '-' }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-space>
                      <a-button type="link" size="small" @click.stop="openDetailModal(record)">编辑</a-button>
                      <a-popconfirm title="确认删除片段？" @confirm="deleteDetail(record.id)">
                        <a-button type="link" size="small" danger @click.stop>删除</a-button>
                      </a-popconfirm>
                    </a-space>
                  </template>
                </template>
              </a-table>
            </a-card>
          </template>
          <a-empty v-else description="请选择左侧检查记录" />
        </a-col>
      </a-row>
    </a-card>

    <a-modal
      v-model:open="detailModalOpen"
      :title="hasSelection ? '新增转化片段 - 来自文本选区' : '转化片段'"
      @ok="saveDetail"
      :confirm-loading="savingDetail"
    >
      <a-space direction="vertical" style="width: 100%">
        <a-input v-model:value="detailForm.raw_fragment" placeholder="原始片段" />
        <a-input v-model:value="detailForm.converted_fragment" placeholder="转化片段" />
        <a-space>
          <a-input-number v-model:value="detailForm.raw_start" placeholder="起始位置" />
          <a-input-number v-model:value="detailForm.raw_end" placeholder="结束位置" />
        </a-space>
        <a-select v-model:value="detailForm.category" :options="categoryOptions" placeholder="分类" />
        <a-select v-model:value="detailForm.action_type" :options="actionOptions" placeholder="动作" />
        <a-space>
          <a-input v-model:value="detailForm.rule_id" placeholder="规则ID" />
          <a-input v-model:value="detailForm.rule_version" placeholder="规则版本" />
        </a-space>
        <a-select v-model:value="detailForm.risk_level" :options="riskLevelOptions" placeholder="风险等级" />
        <a-select v-model:value="detailForm.risk_type" allow-clear :options="riskTypeOptions" placeholder="风险类型" />
        <a-select v-model:value="detailForm.manual_judgement" allow-clear :options="judgeOptions" placeholder="人工判定" />
        <a-textarea v-model:value="detailForm.note" :rows="3" placeholder="备注" />
      </a-space>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { conversionEvalApi, patientApi } from '@/api/client'
import { buildConvertedSegments, buildReferenceSegments, judgeAllFragments, type FragmentMatchResult } from './textSegments'
import AudioPlayer from '@/components/AudioPlayer/index.vue'

const route = useRoute()
const router = useRouter()
const batchId = Number(route.params.id)

const batch = ref<any>(null)
const currentRecordId = ref<number | null>(null)
const detail = ref<any>(null)
const editingConverted = ref(false)
const judging = ref(false)
const converting = ref(false)
const calculating = ref(false)
const detailModalOpen = ref(false)
const savingDetail = ref(false)
const editingDetailId = ref<number | null>(null)
const detailForm = reactive<any>({})
const selectedDetailId = ref<number | null>(null)

// 录音相关
const currentSegs = ref<any[]>([])

// 文本选区相关
const rawTextRef = ref<HTMLElement | null>(null)
const convertedTextRef = ref<HTMLElement | null>(null)
const selectedRawText = ref('')
const selectedRawStart = ref<number | null>(null)
const selectedRawEnd = ref<number | null>(null)
const selectedConvertedText = ref('')
const selectedConvertedStart = ref<number | null>(null)
const selectedConvertedEnd = ref<number | null>(null)

const hasSelection = computed(() => selectedRawText.value || selectedConvertedText.value)

const reviewStatusOptions = [
  { label: '待审校', value: 'pending' },
  { label: '已审校', value: 'reviewed' },
  { label: '已确认', value: 'approved' },
]
const categoryOptions = [
  { label: '医学术语', value: 'medical_term' },
  { label: '数字格式', value: 'number_format' },
  { label: '尺寸格式', value: 'size_format' },
  { label: '左右归属', value: 'left_right' },
  { label: '否定表达', value: 'negation' },
  { label: '医疗决策', value: 'clinical_decision' },
  { label: '噪声处理', value: 'noise' },
  { label: '其他', value: 'other' },
]
const actionOptions = [
  { label: '替换', value: 'replace' },
  { label: '插入', value: 'insert' },
  { label: '删除', value: 'delete' },
  { label: '格式化', value: 'format' },
  { label: '候选', value: 'candidate' },
  { label: '未变化', value: 'no_change' },
]
const riskLevelOptions = [{ label: '低', value: 'low' }, { label: '中', value: 'medium' }, { label: '高', value: 'high' }]
const riskTypeOptions = [
  { label: '数字错误', value: 'number_error' },
  { label: '左右侧', value: 'left_right' },
  { label: '否定词', value: 'negation' },
  { label: '医疗决策', value: 'clinical_decision' },
]
const judgeOptions = [
  { label: '正确转化', value: 'correct' },
  { label: '错误转化', value: 'wrong' },
  { label: '应转未转', value: 'missed' },
  { label: '不应转化', value: 'over_converted' },
  { label: '未变化', value: 'unchanged' },
]
const detailColumns = [
  { title: '原文', dataIndex: 'raw_fragment', key: 'raw_fragment' },
  { title: '转化后', dataIndex: 'converted_fragment', key: 'converted_fragment' },
  { title: '分类', dataIndex: 'category', key: 'category' },
  { title: '动作', dataIndex: 'action_type', key: 'action_type' },
  { title: '规则', dataIndex: 'rule_id', key: 'rule_id' },
  { title: '判定', key: 'judge', width: 140 },
  { title: '专家匹配', key: 'match', width: 100 },
  { title: '风险', key: 'risk' },
  { title: '操作', key: 'action', width: 120 },
]
const annotationColumns = [
  { title: '标记文本', key: 'text' },
  { title: '类型', key: 'type', width: 100 },
  { title: '备注', dataIndex: 'note', key: 'note', ellipsis: true },
]

// 转化片段匹配结果
const fragmentMatchResults = computed<FragmentMatchResult[]>(() =>
  judgeAllFragments(detail.value?.details || [], detail.value?.reference_text || '')
)

// 转化后 ASR 分段（支持高亮选中片段）
const convertedSegments = computed(() =>
  buildConvertedSegments(detail.value?.converted_text, detail.value?.details, selectedDetailId.value)
)

// 专家标准 ASR 分段（只显示 annotations 标记，不做全文 diff）
const diffSegments = computed(() =>
  buildReferenceSegments(detail.value?.reference_text, detail.value?.reference_annotations)
)

// 获取转化片段的匹配状态
function getFragmentMatchStatus(detailId: number): FragmentMatchResult | undefined {
  return fragmentMatchResults.value.find(m => m.detailId === detailId)
}

// 清理函数
function clearSelection() {
  selectedRawText.value = ''
  selectedRawStart.value = null
  selectedRawEnd.value = null
  selectedConvertedText.value = ''
  selectedConvertedStart.value = null
  selectedConvertedEnd.value = null
}

// 点击外部时清空选区
function handleClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.text-panel') && !target.closest('.selection-bar') && !target.closest('.ant-modal')) {
    clearSelection()
  }
}

onMounted(() => {
  document.addEventListener('mouseup', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('mouseup', handleClickOutside)
})

loadBatch()

async function loadBatch() {
  batch.value = await conversionEvalApi.getBatch(batchId)
  if (batch.value?.records?.length) {
    selectRecord(batch.value.records[0].id)
  }
}

async function selectRecord(id: number) {
  currentRecordId.value = id
  editingConverted.value = false
  selectedDetailId.value = null
  clearSelection()

  // 加载详情
  detail.value = await conversionEvalApi.getRecord(id)

  // 加载录音
  await loadRecordSegs(id)
}

async function loadRecordSegs(recordId: number) {
  currentSegs.value = []
  try {
    // 获取评估记录的 exam_record_id
    const record = detail.value
    if (!record?.exam_record_id) return

    // 通过 exam_record_id 获取检查记录的录音
    const examId = record.exam_record_id
    const records = await patientApi.listAsrResultsBatch([examId]).catch(() => ({}))
    // 评估记录关联的是 PatientRecord，需要获取其 segs
    // 直接通过 audioApi 获取
    const { audioApi } = await import('@/api/client')
    const allRecords = await audioApi.getRecords().catch(() => [])
    const matchRecord = (allRecords as any[]).find((r: any) => r.id === examId)
    if (matchRecord?.segs?.length) {
      currentSegs.value = matchRecord.segs
    }
  } catch {
    // 静默失败，播放器会显示"无录音"
  }
}

// 文本选区处理
function onRawTextSelect() {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) return

  const text = selection.toString().trim()
  if (!text) return

  // 检查选区是否在原始 ASR 面板内
  const anchorNode = selection.anchorNode as HTMLElement
  if (!rawTextRef.value?.contains(anchorNode)) return

  selectedRawText.value = text
  // 计算在原文中的位置
  const rawText = detail.value?.raw_text || ''
  const startIdx = rawText.indexOf(text)
  if (startIdx !== -1) {
    selectedRawStart.value = startIdx
    selectedRawEnd.value = startIdx + text.length
  } else {
    selectedRawStart.value = null
    selectedRawEnd.value = null
  }
}

function onConvertedTextSelect() {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) return

  const text = selection.toString().trim()
  if (!text) return

  // 检查选区是否在转化后 ASR 面板内
  const anchorNode = selection.anchorNode as HTMLElement
  if (!convertedTextRef.value?.contains(anchorNode)) return

  selectedConvertedText.value = text
  // 计算在转化后文本中的位置
  const convertedText = detail.value?.converted_text || ''
  const startIdx = convertedText.indexOf(text)
  if (startIdx !== -1) {
    selectedConvertedStart.value = startIdx
    selectedConvertedEnd.value = startIdx + text.length
  } else {
    selectedConvertedStart.value = null
    selectedConvertedEnd.value = null
  }
}

function openDetailModal(row?: any) {
  editingDetailId.value = row?.id || null

  if (row) {
    // 编辑模式：使用现有数据
    Object.assign(detailForm, { ...row })
  } else if (hasSelection.value) {
    // 从选区创建
    Object.assign(detailForm, {
      raw_fragment: selectedRawText.value || selectedConvertedText.value || '',
      converted_fragment: selectedConvertedText.value || selectedRawText.value || '',
      raw_start: selectedRawStart.value ?? selectedConvertedStart.value ?? undefined,
      raw_end: selectedRawEnd.value ?? selectedConvertedEnd.value ?? undefined,
      category: 'medical_term',
      action_type: 'replace',
      rule_id: '',
      rule_version: detail.value?.conversion_version || 'manual',
      risk_level: 'low',
      risk_type: undefined,
      manual_judgement: undefined,
      note: '',
    })
  } else {
    // 空表单
    Object.assign(detailForm, {
      raw_fragment: '',
      converted_fragment: '',
      raw_start: undefined,
      raw_end: undefined,
      category: 'medical_term',
      action_type: 'replace',
      rule_id: '',
      rule_version: detail.value?.conversion_version || 'manual',
      risk_level: 'low',
      risk_type: undefined,
      manual_judgement: undefined,
      note: '',
    })
  }

  detailModalOpen.value = true
}

async function saveConvertedText() {
  if (!detail.value) return
  await conversionEvalApi.updateRecord(detail.value.id, { converted_text: detail.value.converted_text })
  message.success('转化文本已保存')
}

async function saveRecordStatus() {
  if (!detail.value) return
  await conversionEvalApi.updateRecord(detail.value.id, { review_status: detail.value.review_status })
  await loadBatch()
}

async function saveDetail() {
  if (!detail.value) return
  savingDetail.value = true
  try {
    if (editingDetailId.value) {
      await conversionEvalApi.updateDetail(editingDetailId.value, detailForm)
    } else {
      await conversionEvalApi.addDetail(detail.value.id, detailForm)
    }
    detailModalOpen.value = false
    clearSelection()
    await selectRecord(detail.value.id)
  } finally {
    savingDetail.value = false
  }
}

async function deleteDetail(id: number) {
  await conversionEvalApi.deleteDetail(id)
  if (selectedDetailId.value === id) selectedDetailId.value = null
  await selectRecord(detail.value.id)
}

async function setManualJudge(record: any, value: string) {
  await conversionEvalApi.updateDetail(record.id, { manual_judgement: value || undefined })
  await selectRecord(detail.value.id)
}

// 点击转化片段行 → 高亮对应文本
function onRowClick(record: any) {
  selectedDetailId.value = selectedDetailId.value === record.id ? null : record.id
}

function getRowClassName(record: any) {
  return record.id === selectedDetailId.value ? 'selected-row' : ''
}

// 转化后 ASR 分段样式
function getConvertedClass(seg: any) {
  if (seg.type === 'highlight') return 'converted-highlight highlight-selected'
  if (seg.type === 'converted') return 'converted-highlight'
  return ''
}

async function autoJudge() {
  if (!detail.value) return
  judging.value = true
  try {
    detail.value = await conversionEvalApi.autoJudge(detail.value.id)
    message.success('自动判定完成')
  } finally {
    judging.value = false
  }
}

async function calculateMetrics() {
  if (!detail.value) return
  calculating.value = true
  try {
    const metrics = await conversionEvalApi.calculateMetrics(detail.value.id)
    detail.value.metrics_summary = metrics
    message.success('指标已计算')
  } finally {
    calculating.value = false
  }
}

async function runConversion() {
  if (!detail.value) return
  converting.value = true
  try {
    detail.value = await conversionEvalApi.runConversion(detail.value.id)
    message.success('转化引擎运行完成')
  } finally {
    converting.value = false
  }
}

// 批量评估/重算（合并自动判定 + 计算指标）
async function batchEvaluate() {
  judging.value = true
  calculating.value = true
  try {
    const judgeRes = await conversionEvalApi.batchAutoJudge(batchId)
    message.success(`已自动判定 ${judgeRes.processed} 条`)

    const metricsRes = await conversionEvalApi.batchCalculateMetrics(batchId)
    message.success(`已计算 ${metricsRes.record_count} 条，平均准确率 ${percent(metricsRes.average_accuracy)}`)

    await loadBatch()
    await reloadCurrent()
  } finally {
    judging.value = false
    calculating.value = false
  }
}

async function batchRunConversion() {
  converting.value = true
  try {
    const ids = (batch.value?.records || []).map((r: any) => r.id)
    const res = await conversionEvalApi.batchRunConversion(ids)
    message.success(`已运行转化引擎 ${res.processed} 条`)
    await loadBatch()
    await reloadCurrent()
  } finally {
    converting.value = false
  }
}

function confirmDeleteBatch() {
  Modal.confirm({
    title: '确认删除该批次？',
    content: '删除后不可恢复，批次及其转化记录、片段、审校和指标将一并删除；原始检查记录、ASR结果和专家标准ASR不受影响。',
    okText: '删除',
    okType: 'danger',
    onOk: deleteBatch,
  })
}

async function reloadCurrent() {
  if (currentRecordId.value) await selectRecord(currentRecordId.value)
}

async function deleteBatch() {
  await conversionEvalApi.deleteBatch(batchId)
  message.success('批次已删除')
  goBack()
}

function goBack() {
  router.push('/conversion-eval')
}

function referenceMarkClass(type?: string) {
  if (type === 'red') return 'ref-mark ref-mark-red'
  if (type === 'orange') return 'ref-mark ref-mark-orange'
  if (type === 'green') return 'ref-mark ref-mark-green'
  return ''
}

function annotationTypeText(type?: string) {
  return type === 'red' ? '标红' : type === 'orange' ? '备注' : type === 'green' ? '正常' : '标红'
}

function accuracyColor(value: any) {
  const num = Number(value || 0)
  if (num >= 0.9) return 'green'
  if (num >= 0.7) return 'orange'
  return 'red'
}

function percent(value: any) {
  const num = Number(value || 0)
  return `${(num * 100).toFixed(1)}%`
}
</script>

<style scoped>
.batch-detail { width: 100%; min-width: 0; }

/* 主内容区域 */
.main-content {
  height: calc(100vh - 140px);
}

/* 左侧边栏 */
.left-sidebar {
  height: 100%;
}
.sidebar-card {
  height: 100%;
}
.sidebar-card :deep(.ant-card-body) {
  height: calc(100vh - 200px);
  padding: 6px;
  overflow: hidden;
}
.record-list {
  height: 100%;
  overflow-y: auto;
}

/* 右侧详情 */
.attr-row {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.metrics-row {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.action-row {
  margin-bottom: 12px;
}
.text-columns {
  margin-bottom: 12px;
}

/* 文本面板 */
.text-panel {
  min-height: 260px;
  max-height: calc(100vh - 420px);
  overflow: auto;
  white-space: pre-wrap;
  line-height: 1.7;
  padding: 8px;
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 6px;
}

.selectable-text {
  cursor: text;
  user-select: text;
}

/* 选区提示栏 */
.selection-bar {
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.selection-label {
  font-size: 12px;
  color: #52c41a;
  font-weight: 500;
}

/* 转化后 ASR 高亮 */
.converted-highlight {
  color: #f5222d;
  font-weight: 600;
}
.highlight-selected {
  background-color: #fffbe6;
  border-radius: 2px;
  padding: 0 2px;
}

/* 专家标准标记 */
.section-card { margin-top: 12px; }
.ref-mark { border-radius: 2px; padding: 0 1px; }
.ref-mark-red { background-color: #fff1f0; color: #cf1322; border-bottom: 2px solid #ffa39e; }
.ref-mark-orange { background-color: #fff7e6; color: #d46b08; border-bottom: 2px solid #ffd591; }
.ref-mark-green { background-color: #f6ffed; color: #389e0d; border-bottom: 2px solid #b7eb8f; }

/* 匹配说明 */
.match-note {
  font-size: 11px;
  color: #888;
  margin-top: 2px;
  line-height: 1.3;
}
.muted { color: #999; }

/* 左侧列表 */
.record-item {
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 2px;
  border: 1px solid transparent;
  transition: background-color 0.2s;
}
.record-item:hover { background: #f0f5ff; }
.record-item.active { background: #e6f7ff; border-color: #91d5ff; }
.record-id { font-weight: 600; font-size: 13px; }
.record-status { margin-left: 4px; font-size: 10px; line-height: 16px; }
.record-date { font-size: 11px; color: #888; }

/* 表格选中行 */
:deep(.ant-table-tbody tr.selected-row) {
  background: #e6f7ff;
}
</style>
