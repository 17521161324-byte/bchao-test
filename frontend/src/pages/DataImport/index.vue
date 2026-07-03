<template>
  <div class="page-container">
    <!-- 筛选区域 -->
    <a-card style="margin-bottom: 16px">
      <a-row :gutter="16" align="middle">
        <a-col :span="16">
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
        </a-col>
        <a-col :span="8">
          <a-input-search
            v-model:value="searchText"
            placeholder="搜索病历号"
            allow-clear
            @search="onSearch"
          />
        </a-col>
      </a-row>
    </a-card>

    <!-- 数据表格 -->
    <a-card>
      <a-spin v-if="loadingTree" />
      <a-table
        v-else
        :data-source="filteredRecords"
        :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :custom-row="onRowClick"
        row-key="id"
      >
        <a-table-column title="病历号" data-index="record_id" :width="120" />
        <a-table-column title="日期" data-index="date" :width="120">
          <template #default="{ record }">{{ formatDate(record.date) }}</template>
        </a-table-column>
        <a-table-column title="录音" :width="100">
          <template #default="{ record }">
            <a-tag v-if="record.has_audio" color="green">有 ({{ record.segs.length }}段)</a-tag>
            <a-tag v-else color="red">无</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="结果" :width="100">
          <template #default="{ record }">
            <a-tag v-if="record.has_result" color="green">有</a-tag>
            <a-tag v-else color="default">无</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="操作" :width="100">
          <template #default="{ record }">
            <a-button size="small" type="link" danger @click.stop="handleDelete(record)">删除</a-button>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 详情抽屉 -->
    <a-drawer
      :open="drawerOpen"
      title="检查详情"
      placement="right"
      width="800px"
      @close="onDrawerClose"
    >
      <template v-if="selectedRecord">
        <!-- 基本信息 -->
        <a-descriptions :column="2" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="病历号">{{ selectedRecord.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ formatDate(selectedRecord.date) }}</a-descriptions-item>
          <a-descriptions-item label="录音分段">{{ selectedRecord.segs.length }} 段</a-descriptions-item>
          <a-descriptions-item label="B超结果">
            <a-tag v-if="selectedRecord.result" color="green">有</a-tag>
            <a-tag v-else color="default">无</a-tag>
          </a-descriptions-item>
        </a-descriptions>

        <!-- 录音播放器 - 默认展开 -->
        <a-card v-if="selectedRecord.segs.length > 0" size="small" style="margin-bottom: 16px">
          <template #title>录音播放 ({{ selectedRecord.segs.length }}段)</template>
          <AudioPlayer :segs="selectedRecord.segs" />
        </a-card>

        <!-- B 超结果 - 内联编辑 -->
        <template v-if="selectedRecord.result">
          <a-divider>B 超检查结果</a-divider>

          <!-- 查看模式 -->
          <div v-if="!isEditingResult">
            <a-row :gutter="16" style="margin-bottom: 16px">
              <a-col :span="12">
                <a-card size="small" title="右侧卵泡">
                  <a-statistic :value="selectedRecord.result.right_follicle_total" suffix="个" />
                  <div style="color: #666; font-size: 12px; margin-top: 8px">
                    {{ formatFollicles(selectedRecord.result.right_follicles) }}
                  </div>
                </a-card>
              </a-col>
              <a-col :span="12">
                <a-card size="small" title="左侧卵泡">
                  <a-statistic :value="selectedRecord.result.left_follicle_total" suffix="个" />
                  <div style="color: #666; font-size: 12px; margin-top: 8px">
                    {{ formatFollicles(selectedRecord.result.left_follicles) }}
                  </div>
                </a-card>
              </a-col>
            </a-row>

            <a-descriptions :column="2" bordered size="small">
              <a-descriptions-item label="内膜厚度">
                {{ selectedRecord.result.endometrium_thickness != null ? selectedRecord.result.endometrium_thickness + ' mm' : '-' }}
              </a-descriptions-item>
              <a-descriptions-item label="内膜类型">
                {{ selectedRecord.result.endometrium_type || '-' }}
              </a-descriptions-item>
              <a-descriptions-item label="右卵巢">
                <span v-if="selectedRecord.result.right_ovary_length && selectedRecord.result.right_ovary_width">
                  {{ selectedRecord.result.right_ovary_length }} × {{ selectedRecord.result.right_ovary_width }} mm
                </span>
                <span v-else>-</span>
              </a-descriptions-item>
              <a-descriptions-item label="左卵巢">
                <span v-if="selectedRecord.result.left_ovary_length && selectedRecord.result.left_ovary_width">
                  {{ selectedRecord.result.left_ovary_length }} × {{ selectedRecord.result.left_ovary_width }} mm
                </span>
                <span v-else>-</span>
              </a-descriptions-item>
              <a-descriptions-item label="备注" :span="2">
                {{ selectedRecord.result.remark || '-' }}
              </a-descriptions-item>
            </a-descriptions>

            <a-button type="primary" style="margin-top: 16px" @click="startEdit">
              <EditOutlined /> 编辑结果
            </a-button>
          </div>

          <!-- 编辑模式 -->
          <div v-else>
            <!-- 卵泡编辑 - 左右平行 -->
            <a-row :gutter="16" style="margin-bottom: 16px">
              <a-col :span="12">
                <a-card size="small">
                  <template #title>
                    右侧卵泡 <a-tag color="blue">合计: {{ rightFollicleTotal }} 个</a-tag>
                  </template>
                  <div v-for="(item, idx) in editForm.right_follicles" :key="'r'+idx" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center">
                    <a-input-number v-model:value="item.size" :min="0" :step="0.1" style="width: 100px" placeholder="直径" />
                    <span>×</span>
                    <a-input-number v-model:value="item.count" :min="1" :step="1" style="width: 60px" placeholder="数量" />
                    <a-button size="small" danger @click="editForm.right_follicles.splice(idx, 1)">×</a-button>
                  </div>
                  <a-button size="small" type="dashed" @click="editForm.right_follicles.push({size: 0, count: 1})">+ 添加</a-button>
                </a-card>
              </a-col>
              <a-col :span="12">
                <a-card size="small">
                  <template #title>
                    左侧卵泡 <a-tag color="blue">合计: {{ leftFollicleTotal }} 个</a-tag>
                  </template>
                  <div v-for="(item, idx) in editForm.left_follicles" :key="'l'+idx" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center">
                    <a-input-number v-model:value="item.size" :min="0" :step="0.1" style="width: 100px" placeholder="直径" />
                    <span>×</span>
                    <a-input-number v-model:value="item.count" :min="1" :step="1" style="width: 60px" placeholder="数量" />
                    <a-button size="small" danger @click="editForm.left_follicles.splice(idx, 1)">×</a-button>
                  </div>
                  <a-button size="small" type="dashed" @click="editForm.left_follicles.push({size: 0, count: 1})">+ 添加</a-button>
                </a-card>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="内膜厚度 (mm)" style="margin-bottom: 8px">
                  <a-input-number v-model:value="editForm.endometrium_thickness" :min="0" :step="0.1" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="内膜类型" style="margin-bottom: 8px">
                  <a-select v-model:value="editForm.endometrium_type" allow-clear placeholder="选择类型" style="width: 100%">
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
                <a-form-item label="右卵巢长 (mm)" style="margin-bottom: 8px">
                  <a-input-number v-model:value="editForm.right_ovary_length" :min="0" :step="0.1" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="右卵巢宽 (mm)" style="margin-bottom: 8px">
                  <a-input-number v-model:value="editForm.right_ovary_width" :min="0" :step="0.1" style="width: 100%" />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="左卵巢长 (mm)" style="margin-bottom: 8px">
                  <a-input-number v-model:value="editForm.left_ovary_length" :min="0" :step="0.1" style="width: 100%" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="左卵巢宽 (mm)" style="margin-bottom: 8px">
                  <a-input-number v-model:value="editForm.left_ovary_width" :min="0" :step="0.1" style="width: 100%" />
                </a-form-item>
              </a-col>
            </a-row>
            <a-form-item label="备注" style="margin-bottom: 8px">
              <a-textarea v-model:value="editForm.remark" :rows="2" placeholder="备注信息" />
            </a-form-item>

            <a-space style="margin-top: 16px">
              <a-button type="primary" :loading="editSaving" @click="handleSaveResult">保存</a-button>
              <a-button @click="cancelEdit">取消</a-button>
            </a-space>
          </div>
        </template>
      </template>
    </a-drawer>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  EditOutlined,
} from '@ant-design/icons-vue'
import { useAppStore } from '@/stores'
import { resultApi } from '@/api/client'
import type { PatientExamination, BUltraResult } from '@/types'
import AudioPlayer from '@/components/AudioPlayer/index.vue'

export default defineComponent({
  name: 'DataImport',
  components: { AudioPlayer },
  setup() {
    const store = useAppStore()
    const route = useRoute()
    const searchText = ref('')

    // Drawer state from store
    const drawerOpen = computed(() => store.drawerOpen)
    const selectedRecord = computed(() => store.selectedRecord)
    const batches = computed(() => store.batches)
    const selectedBatch = computed(() => store.selectedBatch)
    const loadingTree = computed(() => store.loadingTree)
    const allRecords = computed(() => store.records)

    // Filtered records
    const filteredRecords = computed(() => {
      if (!searchText.value.trim()) return allRecords.value
      const q = searchText.value.trim().toLowerCase()
      return allRecords.value.filter((r) => r.record_id.toLowerCase().includes(q))
    })

    onMounted(() => {
      store.fetchBatches()
      store.fetchRecords()
    })

    // Refresh data when navigating back to this page
    watch(() => route.path, (newPath) => {
      if (newPath === '/data') {
        store.fetchRecords()
      }
    })

    // Edit modal state
    const isEditingResult = ref(false)
    const editSaving = ref(false)
    const editForm = reactive({
      right_follicles: [] as {size: number, count: number}[],
      left_follicles: [] as {size: number, count: number}[],
      endometrium_thickness: null as number | null,
      endometrium_type: null as string | null,
      right_ovary_length: null as number | null,
      right_ovary_width: null as number | null,
      left_ovary_length: null as number | null,
      left_ovary_width: null as number | null,
      remark: '',
    })

    const rightFollicleTotal = computed(() =>
      editForm.right_follicles.reduce((sum, f) => sum + f.count, 0)
    )
    const leftFollicleTotal = computed(() =>
      editForm.left_follicles.reduce((sum, f) => sum + f.count, 0)
    )

    onMounted(() => {
      store.fetchBatches()
      store.fetchRecords()
    })

    onActivated(() => {
      // Refresh data when navigating back to this page
      store.fetchRecords()
    })

    function formatDate(d: string): string {
      if (d.length !== 8) return d
      return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
    }

    function formatFollicles(follicles: BUltraResult['right_follicles'] | BUltraResult['left_follicles']): string {
      if (!follicles || !Array.isArray(follicles) || follicles.length === 0) return '-'
      return follicles.map((f) => `${f.size}×${f.count}`).join('  ')
    }

    function onSearch() {
      // Computed property handles filtering
    }

    function onRowClick(record: PatientExamination) {
      return {
        onClick: () => store.openDrawer(record),
        style: { cursor: 'pointer' }
      }
    }

    function onDrawerClose() {
      store.closeDrawer()
    }

    function startEdit() {
      if (!selectedRecord.value?.result) return
      const r = selectedRecord.value.result
      // Deep copy follicle data to ensure reactivity
      editForm.right_follicles = (r.right_follicles || []).map(f => ({size: f.size, count: f.count}))
      editForm.left_follicles = (r.left_follicles || []).map(f => ({size: f.size, count: f.count}))
      editForm.endometrium_thickness = r.endometrium_thickness
      editForm.endometrium_type = r.endometrium_type
      editForm.right_ovary_length = r.right_ovary_length
      editForm.right_ovary_width = r.right_ovary_width
      editForm.left_ovary_length = r.left_ovary_length
      editForm.left_ovary_width = r.left_ovary_width
      editForm.remark = r.remark || ''
      isEditingResult.value = true
    }

    function cancelEdit() {
      isEditingResult.value = false
      editForm.right_follicles = []
      editForm.left_follicles = []
    }

    async function handleSaveResult() {
      if (!selectedRecord.value?.result) return
      editSaving.value = true
      try {
        const payload = {
          right_follicles: editForm.right_follicles,
          left_follicles: editForm.left_follicles,
          endometrium_thickness: editForm.endometrium_thickness,
          endometrium_type: editForm.endometrium_type,
          right_ovary_length: editForm.right_ovary_length,
          right_ovary_width: editForm.right_ovary_width,
          left_ovary_length: editForm.left_ovary_length,
          left_ovary_width: editForm.left_ovary_width,
          remark: editForm.remark,
        }
        await resultApi.update(selectedRecord.value.result.id, payload)
        message.success('保存成功')
        isEditingResult.value = false
        // Refresh data
        await store.fetchRecords()
        // Update selectedRecord.result with fresh data
        if (selectedRecord.value) {
          const fresh = store.records.find(r => r.id === selectedRecord.value!.id)
          if (fresh && fresh.result) {
            selectedRecord.value.result = fresh.result
          }
        }
      } catch {
        message.error('保存失败')
      } finally {
        editSaving.value = false
      }
    }

    async function handleDelete(record: PatientExamination) {
      if (!confirm(`确定删除病历号 ${record.record_id} (${formatDate(record.date)}) 的记录？`)) return
      try {
        await store.deletePatient(record.id)
        message.success('已删除')
      } catch {
        message.error('删除失败')
      }
    }

    return {
      store, searchText, drawerOpen, selectedRecord,
      batches, selectedBatch, loadingTree, allRecords, filteredRecords,
      isEditingResult, editSaving, editForm, rightFollicleTotal, leftFollicleTotal,
      formatDate, formatFollicles, onSearch, onRowClick, onDrawerClose, startEdit, cancelEdit, handleSaveResult, handleDelete,
    }
  }
})
</script>

<style scoped>
</style>
