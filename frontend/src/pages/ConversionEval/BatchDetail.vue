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

      <!-- ASR 转写评估/结构化对比汇总 -->
      <div v-if="batchStructureSummary" class="structure-summary-bar">
        <a-space wrap size="small">
          <span class="summary-label">结构化对比汇总</span>
          <a-tag color="blue">参与对比 {{ batchStructureSummary.compared_count }}/{{ batchStructureSummary.record_count }}</a-tag>
          <a-tag v-if="batchStructureSummary.missing_ground_truth_count" color="default">无GT {{ batchStructureSummary.missing_ground_truth_count }}</a-tag>
          <a-tag v-if="batchStructureSummary.failed_record_count" color="red">失败 {{ batchStructureSummary.failed_record_count }}</a-tag>
          <a-tag v-if="batchStructureSummary.no_text_count" color="default">无文本 {{ batchStructureSummary.no_text_count }}</a-tag>
          <a-divider type="vertical" />
          <a-tag :color="follicleMatchColor(batchStructureSummary.field_summary?.right_follicles)">
            右卵泡 {{ follicleMatchRate(batchStructureSummary.field_summary?.right_follicles) }}
          </a-tag>
          <a-tag :color="follicleMatchColor(batchStructureSummary.field_summary?.left_follicles)">
            左卵泡 {{ follicleMatchRate(batchStructureSummary.field_summary?.left_follicles) }}
          </a-tag>
          <a-divider type="vertical" />
          <a-tag color="orange">缺失 {{ batchStructureSummary.follicle_summary?.missing_total || 0 }}</a-tag>
          <a-tag color="gold">额外 {{ batchStructureSummary.follicle_summary?.extra_total || 0 }}</a-tag>
          <a-tag color="blue">数量差 {{ batchStructureSummary.follicle_summary?.count_mismatch_total || 0 }}</a-tag>
          <a-tag color="purple">疑似串边 {{ batchStructureSummary.follicle_summary?.possible_side_swap_total || 0 }}</a-tag>
        </a-space>
      </div>

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
                  <a-tag
                    v-else-if="recordDiffTag(rec.id).text"
                    :color="recordDiffTag(rec.id).color"
                    class="record-status"
                  >{{ recordDiffTag(rec.id).text }}</a-tag>
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
              <a-select v-model:value="detail.review_status" size="small" style="width: 120px" :options="reviewStatusOptions" @change="saveRecordStatus" />
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

            <!-- 三栏文本 -->
            <a-row :gutter="12" class="text-columns">
              <a-col :span="8">
                <a-card size="small" title="原始 ASR">
                  <div
                    ref="rawTextRef"
                    class="text-panel selectable-text"
                    @mouseup="onRawTextSelect"
                  >
                    <template v-if="businessTextSegments.length">
                      <span
                        v-for="(seg, idx) in businessTextSegments"
                        :key="idx"
                        :class="seg.segment ? businessHighlightClass(seg.segment) : ''"
                        :title="seg.segment ? businessSegmentTitle(seg.segment) : ''"
                      >{{ seg.text }}</span>
                    </template>
                    <template v-else>{{ detail.raw_text || '暂无文本' }}</template>
                  </div>
                </a-card>
              </a-col>
              <a-col :span="8">
                <a-card size="small">
                  <template #title>
                    <a-space>
                      <span>转化后 ASR</span>
                      <a-button size="small" type="primary" :loading="converting" @click="runConversion">重新转化</a-button>
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

            <!-- 业务片段 / 手工标记 -->
            <a-card size="small" class="section-card">
              <template #title>
                <a-space>
                  <span>业务片段 / 手工标记</span>
                  <a-tag color="default">总计 {{ allBusinessSegments.length }}</a-tag>
                  <a-tag color="blue">当前筛选 {{ filteredBusinessSegments.length }}</a-tag>
                  <a-tag color="orange">人工 {{ manualBusinessSegments.length }}</a-tag>
                </a-space>
              </template>

              <a-tabs v-model:activeKey="businessActiveTab" size="small">
                <a-tab-pane key="segments" tab="片段标记">
                  <div class="filter-group">
                    <div class="filter-line">
                      <span class="filter-label">类型：</span>
                      <a-radio-group v-model:value="businessFilter" size="small" button-style="solid" class="filter-row">
                        <a-radio-button v-for="item in businessFilterOptions" :key="item.value" :value="item.value">
                          {{ item.label }}
                        </a-radio-button>
                      </a-radio-group>
                    </div>
                    <div class="filter-line">
                      <span class="filter-label">字段：</span>
                      <a-radio-group v-model:value="fieldFilter" size="small" class="filter-row field-filter-row">
                        <a-radio-button v-for="item in fieldFilterOptionsWithCount" :key="item.value" :value="item.value">
                          {{ item.label }} <span class="field-count">{{ item.count }}</span>
                        </a-radio-button>
                      </a-radio-group>
                    </div>
                  </div>

                  <!-- 选区提示 -->
                  <div v-if="selectedRawText" class="selection-bar">
                    <a-space>
                      <span class="selection-label">当前选区：</span>
                      <a-tag v-if="selectedRawText" color="blue">原始：{{ selectedRawText.slice(0, 30) }}{{ selectedRawText.length > 30 ? '...' : '' }}</a-tag>
                      <a-button size="small" type="primary" @click="openDetailModal()">使用选区新增手工标记</a-button>
                      <a-button size="small" @click="clearSelection">清空选区</a-button>
                    </a-space>
                  </div>
                  <a-button v-else size="small" type="primary" class="segment-add-btn" @click="openDetailModal()">新增手工标记</a-button>

                  <a-table
                    row-key="idx"
                    size="small"
                    :columns="businessSegmentColumns"
                    :data-source="filteredBusinessSegments"
                    :pagination="{ pageSize: 20, showSizeChanger: true, pageSizeOptions: ['10', '20', '50', '100'] }"
                    :scroll="{ x: 1100 }"
                  >
                    <template #bodyCell="{ column, record }">
                      <template v-if="column.key === 'segment_type'">
                        <a-tag :color="businessTypeColor(record.segment_type)">{{ businessTypeText(record.segment_type) }}</a-tag>
                      </template>
                      <template v-else-if="column.key === 'source_kind'">
                        <a-tag :color="record.source_kind === 'manual' ? 'orange' : 'blue'">
                          {{ record.source_kind === 'manual' ? '人工' : '自动' }}
                        </a-tag>
                      </template>
                      <template v-else-if="column.key === 'side'">
                        <a-tag v-if="record.side" :color="record.side === 'LEFT' ? 'purple' : 'blue'">
                          {{ record.side === 'LEFT' ? '左' : '右' }}
                        </a-tag>
                        <span v-else class="muted">-</span>
                      </template>
                      <template v-else-if="column.key === 'participates'">
                        <a-tag :color="record.participates ? 'green' : 'default'">{{ record.participates ? '参与' : '不参与' }}</a-tag>
                      </template>
                      <template v-else-if="column.key === 'action'">
                        <a-space v-if="record.source_kind === 'manual'">
                          <a-button type="link" size="small" @click.stop="openDetailModal(record)">编辑</a-button>
                          <a-popconfirm title="确认删除人工标记？" @confirm="deleteDetail(record.detail_id)">
                            <a-button type="link" size="small" danger @click.stop>删除</a-button>
                          </a-popconfirm>
                        </a-space>
                        <span v-else class="muted">-</span>
                      </template>
                    </template>
                  </a-table>
                </a-tab-pane>
                <a-tab-pane key="structure" tab="结构化对比">
                  <a-spin :spinning="loadingStructureCompare">
                    <a-empty v-if="!businessStructureCompare?.ground_truth" description="暂无真实 B 超结果" :image="false" />
                    <template v-else>
                      <div class="structure-summary">
                        <a-tag :color="accuracyColor(businessStructureCompare?.comparison?.accuracy)">
                          准确率 {{ percent(businessStructureCompare?.comparison?.accuracy) }}
                        </a-tag>
                        <a-tag color="blue">正确 {{ businessStructureCompare?.comparison?.correct_fields || 0 }} / {{ businessStructureCompare?.comparison?.total_fields || 0 }}</a-tag>
                        <a-tag>来源：{{ businessStructureCompare?.text_source === 'converted' ? '转化后 ASR' : '原始 ASR' }}</a-tag>
                      </div>
                      <a-table
                        row-key="field"
                        size="small"
                        :columns="structureCompareColumns"
                        :data-source="structureCompareRows"
                        :pagination="false"
                        :scroll="{ x: 900 }"
                      >
                        <template #bodyCell="{ column, record }">
                          <template v-if="column.key === 'status'">
                            <a-tag :color="record.match ? 'green' : 'red'">{{ record.match ? '✅ 匹配' : '❌ 不匹配' }}</a-tag>
                          </template>
                          <template v-else-if="column.key === 'extracted'">
                            <span :class="{ 'compare-mismatch': !record.match }">{{ record.extractedText }}</span>
                          </template>
                          <template v-else-if="column.key === 'truth'">
                            <span>{{ record.truthText }}</span>
                          </template>
                          <template v-else-if="column.key === 'diff'">
                            <template v-if="record.follicleDiff">
                              <span v-if="record.follicleDiff.match" class="muted">一致</span>
                              <template v-else>
                                <div class="follicle-diff-summary">{{ formatFollicleDiffSummary(record.follicleDiff) }}</div>
                                <a-collapse v-if="follicleDiffSections(record.follicleDiff).length" ghost size="small" class="follicle-diff-collapse">
                                  <a-collapse-panel
                                    v-for="sec in follicleDiffSections(record.follicleDiff)"
                                    :key="sec.key"
                                    :header="sec.label"
                                  >
                                    <div class="follicle-diff-items">
                                      <a-tag v-for="(item, i) in sec.items" :key="i" :color="sec.color">{{ item }}</a-tag>
                                    </div>
                                  </a-collapse-panel>
                                </a-collapse>
                              </template>
                            </template>
                            <span v-else class="muted">{{ record.diffText || '-' }}</span>
                          </template>
                        </template>
                      </a-table>
                    </template>
                  </a-spin>
                </a-tab-pane>
              </a-tabs>
            </a-card>
          </template>
          <a-empty v-else description="请选择左侧检查记录" />
        </a-col>
      </a-row>
    </a-card>

    <a-modal
      v-model:open="detailModalOpen"
      :title="editingDetailId ? '编辑手工业务片段' : '新增手工业务片段'"
      @ok="saveDetail"
      :confirm-loading="savingDetail"
      width="820px"
      :body-style="{ padding: '16px 20px' }"
      class="detail-modal"
    >
      <a-alert type="info" show-icon message="可先在原始 ASR 中选中文本，再新增；如自动定位漏识别，也可以直接补录片段。" style="margin-bottom: 16px" />
      <a-form layout="vertical" :label-col="{ style: { marginBottom: '4px' } }">
        <!-- 第一行：类型、字段 -->
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="类型">
              <a-select v-model:value="detailForm.segment_type" :options="manualSegmentTypeOptions" placeholder="选择类型" @change="onManualTypeChange" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="字段">
              <a-select
                v-model:value="detailForm.field_code"
                :options="manualFieldOptions"
                placeholder="选择字段"
                show-search
                :filter-option="(input: string, option: any) => option.label.toLowerCase().includes(input.toLowerCase())"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <!-- 第二行：原文片段、标准/归一值 -->
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="原文片段">
              <a-textarea v-model:value="detailForm.raw_fragment" :rows="4" placeholder="输入或从原始 ASR 选中的片段" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="标准/归一值">
              <a-textarea v-model:value="detailForm.converted_fragment" :rows="4" placeholder="可填写标准化后的值；不需要转化可与原文一致" />
            </a-form-item>
          </a-col>
        </a-row>
        <!-- 第三行：起止位置、参与抽取、进入候选池 -->
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="起始位置">
              <a-input-number v-model:value="detailForm.raw_start" style="width: 100%" :min="0" placeholder="字符位置" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="结束位置">
              <a-input-number v-model:value="detailForm.raw_end" style="width: 100%" :min="0" placeholder="字符位置" />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item label="参与抽取">
              <a-switch v-model:checked="detailForm.participates" checked-children="是" un-checked-children="否" />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item label="候选池">
              <a-switch v-model:checked="detailForm.optimize_candidate" checked-children="是" un-checked-children="否" />
            </a-form-item>
          </a-col>
        </a-row>
        <!-- 第四行：原因、状态 -->
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="问题原因/归因">
              <a-select v-model:value="detailForm.reason" allow-clear :options="manualReasonOptions" placeholder="选择原因" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="标记状态">
              <a-select v-model:value="detailForm.manual_judgement" :options="manualStatusOptions" placeholder="选择状态" />
            </a-form-item>
          </a-col>
        </a-row>
        <!-- 第五行：备注（全宽） -->
        <a-form-item label="备注">
          <a-textarea v-model:value="detailForm.note" :rows="3" placeholder="补充说明" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch, onMounted, onBeforeUnmount } from 'vue'
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
const businessActiveTab = ref('segments')
const businessStructureCompare = ref<any>(null)
const loadingStructureCompare = ref(false)
const batchStructureSummary = ref<any>(null)

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
const businessSegments = ref<any[]>([])
const businessFilter = ref('all')
const fieldFilter = ref('all')

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
const businessFilterOptions = [
  { label: '全部', value: 'all' },
  { label: '医学名词', value: 'medical_term' },
  { label: '定位词', value: 'locator' },
  { label: '医疗数据', value: 'medical_data' },
  { label: '噪声处理', value: 'noise' },
]
const manualSegmentTypeOptions = businessFilterOptions.filter(item => item.value !== 'all')
const manualReasonOptions = [
  { label: '近义词/ASR误识别', value: '近义词/ASR误识别' },
  { label: '数字格式', value: '数字格式' },
  { label: '尺寸格式', value: '尺寸格式' },
  { label: '左右归属', value: '左右归属' },
  { label: 'ASR缺失', value: 'ASR缺失' },
  { label: '噪声口语', value: '噪声口语' },
  { label: '其他', value: '其他' },
]
const manualStatusOptions = [
  { label: '待处理', value: 'pending' },
  { label: '已确认', value: 'confirmed' },
  { label: '需优化', value: 'needs_optimization' },
  { label: '不参与', value: 'ignored' },
]
const fieldOptionsByType: Record<string, { label: string; value: string }[]> = {
  medical_term: [
    { label: '内膜', value: 'endometrium' },
    { label: '左卵巢', value: 'left_ovary' },
    { label: '右卵巢', value: 'right_ovary' },
  ],
  locator: [
    { label: '左右定位/换边', value: 'side_switch' },
  ],
  medical_data: [
    { label: '内膜厚度', value: 'endometrium_thickness' },
    { label: '内膜类型', value: 'endometrium_type' },
    { label: '左卵巢大小', value: 'left_ovary_size' },
    { label: '右卵巢大小', value: 'right_ovary_size' },
    { label: '左卵泡', value: 'left_follicles' },
    { label: '右卵泡', value: 'right_follicles' },
    { label: '备注', value: 'remark' },
  ],
  noise: [
    { label: '噪声', value: 'noise' },
  ],
}
const businessSegmentColumns = [
  { title: '类型', dataIndex: 'segment_type', key: 'segment_type', width: 100 },
  { title: '来源', key: 'source_kind', width: 80 },
  { title: '字段', dataIndex: 'field_code', key: 'field_code', width: 150, customRender: ({ text }: any) => fieldCodeText(text) },
  { title: '原文片段', dataIndex: 'text', key: 'text', width: 200 },
  { title: '标准/归一', dataIndex: 'normalized', key: 'normalized', width: 180 },
  { title: '侧别', key: 'side', width: 70 },
  { title: '参与抽取', key: 'participates', width: 90 },
  { title: '说明/备注', dataIndex: 'note', key: 'note', ellipsis: true },
  { title: '位置', key: 'position', width: 90, customRender: ({ record }: any) => formatSegmentPosition(record) },
  { title: '操作', key: 'action', width: 120, fixed: 'right' },
]
const structureCompareColumns = [
  { title: '字段', dataIndex: 'label', key: 'label', width: 130 },
  { title: '匹配', key: 'status', width: 110 },
  { title: '业务抽取结果', key: 'extracted', width: 260 },
  { title: '真实 B 超结果', key: 'truth', width: 260 },
  { title: '差异', key: 'diff' },
]
const structureFields = [
  { field: 'endometrium_thickness', label: '内膜厚度' },
  { field: 'endometrium_type', label: '内膜类型' },
  { field: 'right_ovary_size', label: '右卵巢大小', keys: ['right_ovary_length', 'right_ovary_width'] },
  { field: 'left_ovary_size', label: '左卵巢大小', keys: ['left_ovary_length', 'left_ovary_width'] },
  { field: 'right_follicles', label: '右卵泡明细' },
  { field: 'left_follicles', label: '左卵泡明细' },
  { field: 'remark', label: '备注' },
]

const manualFieldOptions = computed(() => fieldOptionsByType[detailForm.segment_type] || fieldOptionsByType.medical_data)
const manualBusinessSegments = computed(() =>
  (detail.value?.details || [])
    .filter((item: any) => item.rule_id === 'manual_business_segment')
    .map(manualDetailToBusinessSegment)
)
const allBusinessSegments = computed(() => [
  ...businessSegments.value.map(item => ({ ...item, source_kind: 'auto' })),
  ...manualBusinessSegments.value,
])
// 根据当前类型筛选，获取对应的字段选项（预定义映射）
const currentFieldOptions = computed(() => {
  if (businessFilter.value === 'all') {
    // 全部类型时，合并所有字段
    const allFields = new Set<string>()
    for (const fields of Object.values(fieldOptionsByType)) {
      for (const f of fields) allFields.add(f.value)
    }
    return Array.from(allFields).map(f => ({ label: fieldCodeText(f), value: f }))
  }
  return fieldOptionsByType[businessFilter.value] || []
})

// 带数量统计的字段筛选选项
const fieldFilterOptionsWithCount = computed(() => {
  const segments = allBusinessSegments.value
  // 统计当前类型筛选范围内的各字段数量
  const countMap: Record<string, number> = {}
  let totalCount = 0
  for (const item of segments) {
    if (businessFilter.value !== 'all' && item.segment_type !== businessFilter.value) continue
    totalCount++
    if (item.field_code) {
      countMap[item.field_code] = (countMap[item.field_code] || 0) + 1
    }
  }
  // 构建选项：全部字段 + 各字段（带数量）
  const allOption = { label: '全部字段', value: 'all', count: totalCount }
  const fieldOptions = currentFieldOptions.value.map(f => ({
    label: f.label,
    value: f.value,
    count: countMap[f.value] || 0,
  }))
  return [allOption, ...fieldOptions]
})

// 类型筛选变化时，重置字段筛选为"全部"
watch(businessFilter, () => {
  fieldFilter.value = 'all'
})

const filteredBusinessSegments = computed(() => {
  let result = allBusinessSegments.value.map((item, idx) => ({ ...item, idx }))
  if (businessFilter.value !== 'all') result = result.filter(item => item.segment_type === businessFilter.value)
  if (fieldFilter.value !== 'all') result = result.filter(item => item.field_code === fieldFilter.value)
  return result
})
const structureCompareRows = computed(() => {
  const data = businessStructureCompare.value || {}
  const comparisonFields = data.comparison?.fields || {}
  return structureFields.map((item: any) => {
    if (item.keys) {
      const statuses = item.keys.map((key: string) => comparisonFields[key]?.match)
      const match = statuses.length ? statuses.every(Boolean) : false
      const extractedText = item.field === 'right_ovary_size'
        ? formatOvarySize(data.extracted?.right_ovary_length, data.extracted?.right_ovary_width)
        : formatOvarySize(data.extracted?.left_ovary_length, data.extracted?.left_ovary_width)
      const truthText = item.field === 'right_ovary_size'
        ? formatOvarySize(data.ground_truth?.right_ovary_length, data.ground_truth?.right_ovary_width)
        : formatOvarySize(data.ground_truth?.left_ovary_length, data.ground_truth?.left_ovary_width)
      return { field: item.field, label: item.label, match, extractedText, truthText, diffText: match ? '' : '长度/宽度不一致或缺失' }
    }
    const compare = comparisonFields[item.field] || {}
    const extractedValue = data.extracted?.[item.field]
    const truthValue = data.ground_truth?.[item.field]
    const follicleDiff = data.follicle_diff?.[item.field] || null
    return {
      field: item.field,
      label: item.label,
      match: item.field === 'remark' ? normalizeDisplayValue(extractedValue) === normalizeDisplayValue(truthValue) : !!compare.match,
      extractedText: formatStructureValue(item.field, extractedValue),
      truthText: formatStructureValue(item.field, truthValue),
      diffText: follicleDiff ? (follicleDiff.match ? '' : formatFollicleDiffSummary(follicleDiff)) : diffText(compare.diff),
      follicleDiff,
    }
  })
})
const businessTextSegments = computed(() => {
  const text = detail.value?.raw_text || ''
  if (!text) return []
  const active = allBusinessSegments.value
    .filter(item => item.start >= 0 && item.end > item.start)
    .sort((a, b) => a.start - b.start || b.end - a.end)
  const pieces: any[] = []
  let pos = 0
  for (const seg of active) {
    if (seg.start < pos) continue
    if (seg.start > pos) pieces.push({ text: text.slice(pos, seg.start) })
    pieces.push({ text: text.slice(seg.start, seg.end), segment: seg })
    pos = seg.end
  }
  if (pos < text.length) pieces.push({ text: text.slice(pos) })
  return pieces
})

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
  await loadBatchSummary()
  if (batch.value?.records?.length) {
    selectRecord(batch.value.records[0].id)
  }
}

async function loadBatchSummary() {
  batchStructureSummary.value = null
  try {
    batchStructureSummary.value = await conversionEvalApi.getBatchStructureSummary(batchId)
  } catch {
    // 汇总接口失败时降级：仅隐藏汇总条与记录差异标签，不阻断单条详情
    batchStructureSummary.value = null
  }
}

async function selectRecord(id: number) {
  currentRecordId.value = id
  editingConverted.value = false
  selectedDetailId.value = null
  clearSelection()

  // 加载详情
  detail.value = await conversionEvalApi.getRecord(id)
  await loadBusinessSegments(id)
  await loadBusinessStructureCompare(id)

  // 加载录音
  await loadRecordSegs(id)
}

async function loadBusinessSegments(recordId: number) {
  businessSegments.value = []
  try {
    const res = await conversionEvalApi.getBusinessSegments(recordId, 'raw')
    businessSegments.value = res?.segments || []
  } catch {
    businessSegments.value = []
  }
}

async function loadBusinessStructureCompare(recordId: number) {
  businessStructureCompare.value = null
  loadingStructureCompare.value = true
  try {
    businessStructureCompare.value = await conversionEvalApi.getBusinessStructureCompare(recordId)
  } catch {
    businessStructureCompare.value = null
  } finally {
    loadingStructureCompare.value = false
  }
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

  const text = selection.toString()
  if (!text) return

  // 检查选区是否在原始 ASR 面板内
  const anchorNode = selection.anchorNode as HTMLElement
  if (!rawTextRef.value?.contains(anchorNode)) return

  selectedRawText.value = text
  const range = selection.getRangeAt(0)
  const beforeRange = range.cloneRange()
  beforeRange.selectNodeContents(rawTextRef.value)
  beforeRange.setEnd(range.startContainer, range.startOffset)
  const startIdx = beforeRange.toString().length
  selectedRawStart.value = startIdx
  selectedRawEnd.value = startIdx + text.length
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
  editingDetailId.value = row?.detail_id || null

  if (row) {
    // 编辑模式：使用现有数据
    Object.assign(detailForm, {
      segment_type: row.segment_type || 'medical_data',
      field_code: row.field_code || defaultFieldForType(row.segment_type),
      raw_fragment: row.text || '',
      converted_fragment: row.normalized || row.text || '',
      raw_start: Number.isFinite(row.start) && row.start >= 0 ? row.start : undefined,
      raw_end: Number.isFinite(row.end) && row.end >= 0 ? row.end : undefined,
      participates: row.participates !== false,
      optimize_candidate: row.optimize_candidate !== false && row.participates !== false,
      reason: row.reason || undefined,
      manual_judgement: row.manual_judgement || 'pending',
      note: row.note || '',
    })
  } else if (selectedRawText.value) {
    // 从选区创建
    Object.assign(detailForm, {
      segment_type: 'medical_data',
      field_code: 'left_follicles',
      raw_fragment: selectedRawText.value || '',
      converted_fragment: selectedRawText.value || '',
      raw_start: selectedRawStart.value ?? undefined,
      raw_end: selectedRawEnd.value ?? undefined,
      participates: true,
      optimize_candidate: true,
      reason: undefined,
      manual_judgement: 'pending',
      note: '',
    })
  } else {
    // 空表单
    Object.assign(detailForm, {
      segment_type: 'medical_data',
      field_code: 'left_follicles',
      raw_fragment: '',
      converted_fragment: '',
      raw_start: undefined,
      raw_end: undefined,
      participates: true,
      optimize_candidate: true,
      reason: undefined,
      manual_judgement: 'pending',
      note: '',
    })
  }

  detailModalOpen.value = true
}

async function saveConvertedText() {
  if (!detail.value) return
  await conversionEvalApi.updateRecord(detail.value.id, { converted_text: detail.value.converted_text })
  await loadBusinessStructureCompare(detail.value.id)
  await loadBatchSummary()
  message.success('转化文本已保存')
}

async function saveRecordStatus() {
  if (!detail.value) return
  await conversionEvalApi.updateRecord(detail.value.id, { review_status: detail.value.review_status })
  await loadBatch()
}

async function saveDetail() {
  if (!detail.value) return
  if (!String(detailForm.raw_fragment || '').trim()) {
    message.warning('请填写原始片段')
    return
  }
  if (!detailForm.field_code) {
    message.warning('请选择字段')
    return
  }
  savingDetail.value = true
  try {
    const rawText = detail.value.raw_text || ''
    const start = typeof detailForm.raw_start === 'number' ? detailForm.raw_start : null
    const end = typeof detailForm.raw_end === 'number' ? detailForm.raw_end : null
    const payload = {
      raw_fragment: detailForm.raw_fragment,
      converted_fragment: detailForm.converted_fragment || detailForm.raw_fragment,
      raw_start: start,
      raw_end: end,
      context_before: start !== null ? rawText.slice(Math.max(0, start - 20), start) : '',
      context_after: end !== null ? rawText.slice(end, Math.min(rawText.length, end + 20)) : '',
      action_type: 'manual_mark',
      category: detailForm.field_code,
      rule_id: 'manual_business_segment',
      rule_version: detail.value?.conversion_version || 'manual',
      confidence: 1,
      risk_level: 'low',
      risk_type: detailForm.segment_type,
      note: encodeManualNote({
        segment_type: detailForm.segment_type,
        field_code: detailForm.field_code,
        participates: !!detailForm.participates,
        optimize_candidate: !!detailForm.optimize_candidate,
        reason: detailForm.reason || '',
        note: detailForm.note || '',
      }),
      manual_judgement: detailForm.manual_judgement || undefined,
      final_judgement: detailForm.manual_judgement || undefined,
    }
    if (editingDetailId.value) {
      await conversionEvalApi.updateDetail(editingDetailId.value, payload)
    } else {
      await conversionEvalApi.addDetail(detail.value.id, payload)
    }
    detailModalOpen.value = false
    clearSelection()
    await selectRecord(detail.value.id)
    await loadBatchSummary()
  } finally {
    savingDetail.value = false
  }
}

async function deleteDetail(id: number) {
  await conversionEvalApi.deleteDetail(id)
  if (selectedDetailId.value === id) selectedDetailId.value = null
  await selectRecord(detail.value.id)
  await loadBatchSummary()
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
    await loadBusinessSegments(detail.value.id)
    await loadBusinessStructureCompare(detail.value.id)
    await loadBatchSummary()
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

function annotationTypeText(type?: string) {
  return type === 'red' ? '标红' : type === 'orange' ? '备注' : type === 'green' ? '正常' : '标红'
}

function onManualTypeChange() {
  detailForm.field_code = defaultFieldForType(detailForm.segment_type)
  detailForm.participates = detailForm.segment_type === 'medical_data'
  if (!detailForm.converted_fragment) detailForm.converted_fragment = detailForm.raw_fragment
}

function defaultFieldForType(type?: string) {
  const first = (fieldOptionsByType[type || 'medical_data'] || fieldOptionsByType.medical_data)[0]
  return first?.value || 'other'
}

function encodeManualNote(meta: any) {
  const { note, ...rest } = meta
  return `__manual_business_segment__${JSON.stringify(rest)}\n${note || ''}`
}

function parseManualNote(note?: string | null) {
  const text = note || ''
  if (!text.startsWith('__manual_business_segment__')) return { note: text }
  const lineEnd = text.indexOf('\n')
  const head = lineEnd >= 0 ? text.slice(0, lineEnd) : text
  const body = lineEnd >= 0 ? text.slice(lineEnd + 1) : ''
  try {
    return { ...JSON.parse(head.replace('__manual_business_segment__', '')), note: body }
  } catch {
    return { note: body || text }
  }
}

function manualDetailToBusinessSegment(item: any) {
  const meta = parseManualNote(item.note)
  const fieldCode = meta.field_code || item.category || 'other'
  return {
    id: `manual-${item.id}`,
    detail_id: item.id,
    source_kind: 'manual',
    segment_type: meta.segment_type || item.risk_type || segmentTypeFromField(fieldCode),
    field_code: fieldCode,
    text: item.raw_fragment || '',
    normalized: item.converted_fragment || item.raw_fragment || '',
    start: item.raw_start ?? -1,
    end: item.raw_end ?? -1,
    side: sideFromField(fieldCode),
    participates: meta.participates ?? fieldCode !== 'noise',
    optimize_candidate: meta.optimize_candidate ?? meta.participates ?? fieldCode !== 'noise',
    reason: meta.reason || '',
    manual_judgement: item.manual_judgement || item.final_judgement || 'pending',
    note: meta.note || '',
  }
}

function segmentTypeFromField(field?: string) {
  if (['endometrium', 'left_ovary', 'right_ovary'].includes(field || '')) return 'medical_term'
  if (['side_switch'].includes(field || '')) return 'locator'
  if (['noise'].includes(field || '')) return 'noise'
  return 'medical_data'
}

function sideFromField(field?: string) {
  if ((field || '').startsWith('left_')) return 'LEFT'
  if ((field || '').startsWith('right_')) return 'RIGHT'
  return ''
}

function normalizeDisplayValue(value: any) {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

function formatOvarySize(length: any, width: any) {
  if (length === null || length === undefined || width === null || width === undefined) return '-'
  return `${formatNumber(length)}×${formatNumber(width)}`
}

function formatNumber(value: any) {
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value ?? '-')
  return Number.isInteger(num) ? String(num) : num.toFixed(1)
}

function formatFollicles(value: any) {
  if (!Array.isArray(value) || !value.length) return '-'
  const total = value.reduce((sum: number, item: any) => sum + Number(item.count || 0), 0)
  const detailText = value.map((item: any) => `${formatNumber(item.size)}×${item.count || 1}`).join('、')
  return `${total}个（${detailText}）`
}

function formatStructureValue(field: string, value: any) {
  if (field === 'right_follicles' || field === 'left_follicles') return formatFollicles(value)
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function diffText(diff: any) {
  if (!diff) return ''
  if (typeof diff === 'object') return JSON.stringify(diff)
  return String(diff)
}

// 批次汇总：记录差异标签映射
const recordDiffMap = computed(() => {
  const map: Record<number, any> = {}
  for (const item of batchStructureSummary.value?.records || []) {
    map[item.record_id] = item
  }
  return map
})

function recordDiffTag(recordId: number) {
  const item = recordDiffMap.value[recordId]
  if (!item) return { color: 'default', text: '' }
  if (item.status === 'no_ground_truth') return { color: 'default', text: '无GT' }
  if (item.status !== 'compared') return { color: 'default', text: '' }
  if (item.right_match && item.left_match) return { color: 'green', text: '卵泡OK' }
  const flags: string[] = []
  if (item.right_side_swap || item.left_side_swap) flags.push('串边?')
  if (!item.right_match) flags.push('右差异')
  if (!item.left_match) flags.push('左差异')
  return { color: flags.includes('串边?') ? 'orange' : 'red', text: flags.join('/') }
}

function follicleMatchRate(summary: any) {
  const match = Number(summary?.match || 0)
  const mismatch = Number(summary?.mismatch || 0)
  const total = match + mismatch
  if (!total) return '-'
  return `${Math.round((match / total) * 100)}% (${match}/${total})`
}

function follicleMatchColor(summary: any) {
  const match = Number(summary?.match || 0)
  const mismatch = Number(summary?.mismatch || 0)
  const total = match + mismatch
  if (!total) return 'default'
  if (mismatch === 0) return 'green'
  if (mismatch <= match) return 'orange'
  return 'red'
}

function formatFollicleDiffSummary(diff: any) {
  return diff?.summary || ''
}

function follicleDiffSections(diff: any) {
  if (!diff) return []
  const sections: any[] = []
  const missing = diff.missing || []
  const extra = diff.extra || []
  const countMismatch = diff.count_mismatch || []
  const swaps = diff.possible_side_swaps || []
  if (missing.length) {
    sections.push({
      key: 'missing',
      label: `缺失项 ${missing.length}`,
      color: 'red',
      items: missing.map((item: any) => `${formatNumber(item.size)}×${item.count}`),
    })
  }
  if (extra.length) {
    sections.push({
      key: 'extra',
      label: `额外项 ${extra.length}`,
      color: 'orange',
      items: extra.map((item: any) => `${formatNumber(item.size)}×${item.count}`),
    })
  }
  if (countMismatch.length) {
    sections.push({
      key: 'count',
      label: `数量差 ${countMismatch.length}`,
      color: 'blue',
      items: countMismatch.map((item: any) => `${formatNumber(item.size)} 识别${item.identified_count} / 真实${item.truth_count}`),
    })
  }
  if (swaps.length) {
    sections.push({
      key: 'swap',
      label: `疑似左右串边 ${swaps.length}`,
      color: 'purple',
      items: swaps.map((item: any) => `${formatNumber(item.size)}×${item.count}`),
    })
  }
  return sections
}

function fieldCodeText(code?: string) {
  const map: any = {
    endometrium: '内膜',
    right_ovary: '右卵巢',
    left_ovary: '左卵巢',
    side_switch: '左右定位',
    endometrium_thickness: '内膜厚度',
    endometrium_type: '内膜类型',
    right_ovary_size: '右卵巢大小',
    left_ovary_size: '左卵巢大小',
    right_follicles: '右卵泡',
    left_follicles: '左卵泡',
    remark: '备注',
    noise: '噪声',
    medical_data: '医疗数据',
    other: '其他',
  }
  return map[code || ''] || code || '-'
}

function businessTypeText(type?: string) {
  const map: any = {
    medical_term: '医学名词',
    locator: '定位词',
    medical_data: '医疗数据',
    noise: '噪声处理',
  }
  return map[type || ''] || type || '-'
}

function businessTypeColor(type?: string) {
  const map: any = {
    medical_term: 'red',
    locator: 'purple',
    medical_data: 'green',
    noise: 'default',
  }
  return map[type || ''] || 'default'
}

function businessHighlightClass(seg: any) {
  return `business-highlight business-${seg.segment_type || 'other'}`
}

function businessSegmentTitle(seg: any) {
  return `${businessTypeText(seg.segment_type)} · ${fieldCodeText(seg.field_code)} · ${seg.normalized ?? seg.text}`
}

function formatSegmentPosition(record: any) {
  if (record.start === undefined || record.start === null || record.start < 0) return '-'
  if (record.end === undefined || record.end === null || record.end < 0) return `${record.start}-`
  return `${record.start}-${record.end}`
}
</script>

<style scoped>
.batch-detail { width: 100%; min-width: 0; }

/* 筛选组 */
.filter-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
  padding: 8px 0 12px;
  margin-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}
.filter-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.filter-label {
  flex: 0 0 auto;
  color: #666;
  font-size: 12px;
  line-height: 24px;
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 0;
  min-width: 0;
}
.field-filter-row :deep(.ant-radio-button-wrapper) {
  padding: 0 8px;
  font-size: 12px;
  margin-bottom: 4px;
}
.field-count {
  margin-left: 3px;
  font-size: 11px;
  color: #888;
}

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
.segment-add-btn {
  margin-bottom: 8px;
}
.structure-summary {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.structure-summary-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
}
.summary-label {
  font-size: 12px;
  font-weight: 600;
  color: #333;
  margin-right: 4px;
}
.follicle-diff-summary {
  color: #cf1322;
  font-size: 12px;
  margin-bottom: 4px;
}
.follicle-diff-collapse {
  background: #fffbe6;
  border-radius: 4px;
}
.follicle-diff-collapse :deep(.ant-collapse-header) {
  padding: 4px 8px !important;
  font-size: 12px;
}
.follicle-diff-items {
  padding: 0 4px 4px;
}
.compare-mismatch {
  color: #cf1322;
  font-weight: 600;
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

/* 业务片段高亮：自动与人工共用同一套颜色 */
.business-highlight {
  border-radius: 3px;
  padding: 0 2px;
  margin: 0 1px;
  font-weight: 600;
}
.business-medical_term { background: #fff1f0; color: #cf1322; border-bottom: 2px solid #ff7875; }
.business-locator { background: #f9f0ff; color: #722ed1; border-bottom: 2px solid #b37feb; }
.business-medical_data { background: #f6ffed; color: #389e0d; border-bottom: 2px solid #95de64; }
.business-noise { background: #f5f5f5; color: #8c8c8c; border-bottom: 2px solid #d9d9d9; }

/* 专家标准标记 */
.section-card { margin-top: 12px; }

/* 弹窗响应式 */
.detail-modal :deep(.ant-modal) {
  max-width: calc(100vw - 48px);
}
.detail-modal :deep(.ant-form-item-label > label) {
  font-size: 13px;
  color: #333;
}
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
