<template>
  <div class="page-container">
    <div class="page-header" style="display: flex; justify-content: space-between; align-items: center">
      <h2>数据管理</h2>
      <a-radio-group v-model:value="viewMode" button-style="solid" size="small">
        <a-radio-button value="browse">数据浏览</a-radio-button>
        <a-radio-button value="verify">
          数据核对
          <a-badge v-if="verification && verification.total_issues > 0" :count="verification.total_issues" size="small" />
        </a-radio-button>
      </a-radio-group>
    </div>

    <!-- 批次选择器 -->
    <a-card style="margin-bottom: 16px">
      <a-space>
        <span style="color: #666">批次：</span>
        <a-checkable-tag :checked="selectedBatch === null" @click="store.selectBatch(null)" style="cursor: pointer">
          全部
        </a-checkable-tag>
        <a-checkable-tag
          v-for="batch in batches"
          :key="batch.date"
          :checked="selectedBatch === batch.date"
          @click="store.selectBatch(batch.date)"
          style="cursor: pointer"
        >
          {{ formatDate(batch.date) }} ({{ batch.patient_count }}人)
        </a-checkable-tag>
      </a-space>
    </a-card>

    <!-- 统计卡片 -->
    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="6">
        <a-card><a-statistic title="日期数" :value="dataStatus?.total_dates ?? 0" /></a-card>
      </a-col>
      <a-col :span="6">
        <a-card><a-statistic title="总病历数" :value="dataStatus?.total_patients ?? 0" /></a-card>
      </a-col>
      <a-col :span="6">
        <a-card>
          <a-statistic title="已匹配" :value="dataStatus?.matched_count ?? 0" :value-style="{ color: '#52c41a' }" />
        </a-card>
      </a-col>
      <a-col :span="6">
        <a-card>
          <a-statistic title="仅录音" :value="dataStatus?.audio_only_count ?? 0" :value-style="{ color: '#faad14' }" />
        </a-card>
      </a-col>
    </a-row>

    <!-- 主体：左右分栏 / 数据核对 -->
    <template v-if="viewMode === 'verify'">
      <a-card>
        <template #extra>
          <a-button size="small" @click="store.fetchVerification"><ReloadOutlined />刷新</a-button>
        </template>
        <a-spin v-if="verifying" />

        <template v-else-if="verification">
          <a-alert
            v-if="verification.total_issues === 0"
            type="success"
            message="数据校验通过，未发现异常"
            show-icon
            style="margin-bottom: 16px"
          />

          <a-table
            v-else
            :data-source="verification.issues"
            :pagination="{ pageSize: 20 }"
            size="small"
            row-key="patient_id"
          >
            <a-table-column title="问题类型" data-index="type" :width="140">
              <template #default="{ record }">
                <a-tag v-if="record.type === 'no_audio_has_result'" color="red">无录音有结果</a-tag>
                <a-tag v-else-if="record.type === 'missing_files'" color="orange">文件缺失</a-tag>
                <a-tag v-else color="blue">重复病历</a-tag>
              </template>
            </a-table-column>
            <a-table-column title="日期" data-index="date" :width="100">
              <template #default="{ record }">{{ formatDate(record.date) }}</template>
            </a-table-column>
            <a-table-column title="病历号" data-index="record_id" :width="120" />
            <a-table-column title="详情" data-index="detail" />
            <a-table-column title="操作" :width="100">
              <template #default="{ record }">
                <a-popconfirm
                  v-if="record.type === 'no_audio_has_result'"
                  title="确定删除此结果？"
                  @confirm="handleDeleteIssue(record)"
                >
                  <a-button size="small" type="link" danger>删除结果</a-button>
                </a-popconfirm>
                <a-button v-else size="small" type="link" @click="handleIgnoreIssue(record)">忽略</a-button>
              </template>
            </a-table-column>
          </a-table>
        </template>
      </a-card>
    </template>

    <!-- 数据浏览模式 -->
    <template v-else>
    <a-row :gutter="16">
      <!-- 左侧：患者列表 -->
      <a-col :span="8">
        <a-card title="患者列表" :body-style="{ padding: 0 }">
          <template #extra>
            <a-input-search
              v-model:value="searchText"
              placeholder="搜索病历号"
              style="width: 180px"
              allow-clear
            />
          </template>

          <a-spin v-if="loadingTree" style="padding: 40px; text-align: center; display: block" />

          <div v-else class="patient-list">
            <div
              v-for="group in filteredGroups"
              :key="group.record_id"
              class="patient-group"
            >
              <div
                class="patient-header"
                :class="{ expanded: expandedGroups[group.record_id] }"
                @click="toggleGroup(group.record_id)"
              >
                <CaretRightOutlined class="expand-icon" :class="{ rotated: expandedGroups[group.record_id] }" />
                <span class="record-id">{{ group.record_id }}</span>
                <a-tag color="blue" size="small">{{ group.examinations.length }}次</a-tag>
              </div>

              <div v-if="expandedGroups[group.record_id]" class="exam-list">
                <div
                  v-for="exam in group.examinations"
                  :key="exam.id"
                  class="exam-item"
                  :class="{ active: selectedExam?.id === exam.id }"
                  @click="store.selectExam(group, exam)"
                >
                  <span class="exam-date">{{ formatDate(exam.date) }}</span>
                  <CheckCircleOutlined v-if="exam.result" class="status-icon matched" />
                  <WarningOutlined v-else class="status-icon audio-only" />
                </div>
              </div>
            </div>

            <a-empty v-if="filteredGroups.length === 0" description="无匹配患者" style="padding: 40px" />
          </div>
        </a-card>
      </a-col>

      <!-- 右侧：详情面板 -->
      <a-col :span="16">
        <a-card v-if="!selectedExam" description="从左侧选择一个检查查看详情" style="min-height: 500px">
          <a-empty description="未选择" />
        </a-card>

        <template v-else>
          <!-- 患者信息头 -->
          <a-card style="margin-bottom: 16px">
            <a-row :gutter="16" align="middle">
              <a-col>
                <span style="font-size: 18px; font-weight: bold">{{ selectedExam.record_id }}</span>
              </a-col>
              <a-col>
                <a-tag color="blue">{{ formatDate(selectedExam.date) }}</a-tag>
              </a-col>
              <a-col>
                <a-tag>录音</a-tag>
              </a-col>
              <a-col v-if="selectedExam.result">
                <a-tag color="green">已匹配结果</a-tag>
              </a-col>
              <a-col v-else>
                <a-tag color="orange">仅录音</a-tag>
              </a-col>
            </a-row>
          </a-card>

          <!-- 录音播放器 -->
          <a-card title="录音播放" style="margin-bottom: 16px">
            <AudioPlayer :segs="selectedExam.segs" />
          </a-card>

          <!-- B 超结果 -->
          <a-card>
            <template #title>
              <span>B 超检查结果 — {{ formatDate(selectedExam.date) }}</span>
            </template>
            <template #extra>
              <a-button v-if="selectedExam.result" size="small" type="link" @click="openEditModal">
                <EditOutlined /> 编辑
              </a-button>
            </template>

            <a-empty v-if="!selectedExam.result" description="暂无结果数据（可上传 xlsx 导入）" />

            <a-descriptions v-else :column="2" bordered size="small" :label-style="{ fontWeight: 500 }">
              <a-descriptions-item label="右侧卵泡">
                <span v-if="selectedExam.result.right_follicle_total > 0">
                  {{ selectedExam.result.right_follicle_total }} 个
                  <span style="color: #666; font-size: 12px">
                    ({{ formatFollicles(selectedExam.result.right_follicles) }})
                  </span>
                </span>
                <span v-else style="color: #999">-</span>
              </a-descriptions-item>

              <a-descriptions-item label="左侧卵泡">
                <span v-if="selectedExam.result.left_follicle_total > 0">
                  {{ selectedExam.result.left_follicle_total }} 个
                  <span style="color: #666; font-size: 12px">
                    ({{ formatFollicles(selectedExam.result.left_follicles) }})
                  </span>
                </span>
                <span v-else style="color: #999">-</span>
              </a-descriptions-item>

              <a-descriptions-item label="内膜厚度">
                {{ selectedExam.result.endometrium_thickness != null ? selectedExam.result.endometrium_thickness + ' mm' : '-' }}
              </a-descriptions-item>

              <a-descriptions-item label="内膜类型">
                {{ selectedExam.result.endometrium_type || '-' }}
              </a-descriptions-item>

              <a-descriptions-item label="右卵巢">
                <span v-if="selectedExam.result.right_ovary_length && selectedExam.result.right_ovary_width">
                  {{ selectedExam.result.right_ovary_length }} × {{ selectedExam.result.right_ovary_width }} mm
                </span>
                <span v-else>-</span>
              </a-descriptions-item>

              <a-descriptions-item label="左卵巢">
                <span v-if="selectedExam.result.left_ovary_length && selectedExam.result.left_ovary_width">
                  {{ selectedExam.result.left_ovary_length }} × {{ selectedExam.result.left_ovary_width }} mm
                </span>
                <span v-else>-</span>
              </a-descriptions-item>

              <a-descriptions-item label="备注" :span="2">
                {{ selectedExam.result.remark || '-' }}
              </a-descriptions-item>
            </a-descriptions>
          </a-card>

          <!-- 编辑结果对话框 -->
          <a-modal
            v-model:open="editModalOpen"
            title="编辑 B 超结果"
            :confirm-loading="editSaving"
            ok-text="保存"
            cancel-text="取消"
            @ok="handleSaveResult"
            width="600px"
          >
            <a-form :model="editForm" layout="vertical" size="small">
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="右侧卵泡总数">
                    <a-input-number v-model:value="editForm.right_follicle_total" :min="0" style="width: 100%" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="左侧卵泡总数">
                    <a-input-number v-model:value="editForm.left_follicle_total" :min="0" style="width: 100%" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="内膜厚度 (mm)">
                    <a-input-number v-model:value="editForm.endometrium_thickness" :min="0" :step="0.1" style="width: 100%" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="内膜类型">
                    <a-select v-model:value="editForm.endometrium_type" allow-clear placeholder="选择类型">
                      <a-select-option value="A">A</a-select-option>
                      <a-select-option value="B">B</a-select-option>
                      <a-select-option value="C">C</a-select-option>
                      <a-select-option value="A-B">A-B</a-select-option>
                      <a-select-option value="B-C">B-C</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
              </a-row>
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="右卵巢长 (mm)">
                    <a-input-number v-model:value="editForm.right_ovary_length" :min="0" :step="0.1" style="width: 100%" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="右卵巢宽 (mm)">
                    <a-input-number v-model:value="editForm.right_ovary_width" :min="0" :step="0.1" style="width: 100%" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-row :gutter="16">
                <a-col :span="12">
                  <a-form-item label="左卵巢长 (mm)">
                    <a-input-number v-model:value="editForm.left_ovary_length" :min="0" :step="0.1" style="width: 100%" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="左卵巢宽 (mm)">
                    <a-input-number v-model:value="editForm.left_ovary_width" :min="0" :step="0.1" style="width: 100%" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="备注">
                <a-textarea v-model:value="editForm.remark" :rows="2" placeholder="备注信息" />
              </a-form-item>
            </a-form>
          </a-modal>
        </template>
      </a-col>
    </a-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import {
  CaretRightOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  EditOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { useAppStore } from '@/stores'
import { resultApi } from '@/api/client'
import { message } from 'ant-design-vue'
import type { PatientGroup, BUltraResult, DataIssue } from '@/types'
import AudioPlayer from '@/components/AudioPlayer/index.vue'

const store = useAppStore()
const { dataStatus, loadingTree, batches, selectedBatch, patientGroups, selectedExam, verification, verifying } = storeToRefs(store)

const searchText = ref('')
const viewMode = ref('browse')
const expandedGroups = ref<Record<string, boolean>>({})

watch(viewMode, (mode) => {
  if (mode === 'verify' && !verification.value) {
    store.fetchVerification()
  }
})

// Edit modal state
const editModalOpen = ref(false)
const editSaving = ref(false)
const editForm = reactive({
  right_follicle_total: 0,
  left_follicle_total: 0,
  endometrium_thickness: null as number | null,
  endometrium_type: null as string | null,
  right_ovary_length: null as number | null,
  right_ovary_width: null as number | null,
  left_ovary_length: null as number | null,
  left_ovary_width: null as number | null,
  remark: '',
})

onMounted(() => {
  store.fetchBatches()
  store.fetchPatients()
  store.fetchDataStatus()
})

const filteredGroups = computed(() => {
  if (!searchText.value.trim()) return patientGroups.value
  const q = searchText.value.trim().toLowerCase()
  return patientGroups.value.filter((g) => g.record_id.toLowerCase().includes(q))
})

function toggleGroup(recordId: string) {
  expandedGroups.value[recordId] = !expandedGroups.value[recordId]
}

function formatDate(d: string): string {
  if (d.length !== 8) return d
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
}

function formatFollicles(follicles: BUltraResult['right_follicles'] | BUltraResult['left_follicles']): string {
  if (!follicles || !Array.isArray(follicles) || follicles.length === 0) return '-'
  return follicles.map((f) => `${f.size}×${f.count}`).join('  ')
}

function openEditModal() {
  if (!selectedExam.value?.result) return
  const r = selectedExam.value.result
  editForm.right_follicle_total = r.right_follicle_total
  editForm.left_follicle_total = r.left_follicle_total
  editForm.endometrium_thickness = r.endometrium_thickness
  editForm.endometrium_type = r.endometrium_type
  editForm.right_ovary_length = r.right_ovary_length
  editForm.right_ovary_width = r.right_ovary_width
  editForm.left_ovary_length = r.left_ovary_length
  editForm.left_ovary_width = r.left_ovary_width
  editForm.remark = r.remark || ''
  editModalOpen.value = true
}

async function handleSaveResult() {
  if (!selectedExam.value?.result) return
  editSaving.value = true
  try {
    await resultApi.update(selectedExam.value.result.id, editForm)
    message.success('保存成功')
    editModalOpen.value = false
    // Update local data
    const r = selectedExam.value.result
    r.right_follicle_total = editForm.right_follicle_total
    r.left_follicle_total = editForm.left_follicle_total
    r.endometrium_thickness = editForm.endometrium_thickness
    r.endometrium_type = editForm.endometrium_type
    r.right_ovary_length = editForm.right_ovary_length
    r.right_ovary_width = editForm.right_ovary_width
    r.left_ovary_length = editForm.left_ovary_length
    r.left_ovary_width = editForm.left_ovary_width
    r.remark = editForm.remark
  } catch {
    message.error('保存失败')
  } finally {
    editSaving.value = false
  }
}

async function handleDeleteIssue(issue: DataIssue) {
  try {
    // Delete the BUltraResult for this patient
    await store.deletePatient(issue.patient_id)
    message.success('已删除')
  } catch {
    message.error('删除失败')
  }
}

function handleIgnoreIssue(issue: DataIssue) {
  message.info('已忽略')
}
</script>

<style scoped>
.patient-list {
  max-height: 600px;
  overflow-y: auto;
}

.patient-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f5f5f5;
  transition: background 0.15s;
}

.patient-header:hover {
  background: #fafafa;
}

.expand-icon {
  transition: transform 0.2s;
  font-size: 12px;
}

.expand-icon.rotated {
  transform: rotate(90deg);
}

.record-id {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}

.exam-list {
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}

.exam-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px 8px 40px;
  cursor: pointer;
  font-size: 13px;
  border-left: 3px solid transparent;
  transition: background 0.15s;
}

.exam-item:hover {
  background: #e6f4ff;
}

.exam-item.active {
  background: #e6f4ff;
  border-left-color: #1677ff;
}

.exam-date {
  font-weight: 500;
}

.exam-count {
  color: #999;
  font-size: 12px;
  flex: 1;
}

.status-icon.matched {
  color: #52c41a;
}

.status-icon.audio-only {
  color: #faad14;
}
</style>
