<template>
  <div class="page-container">
    <!-- 筛选区域 -->
    <a-card style="margin-bottom: 16px">
      <a-row :gutter="16" align="middle">
        <a-col :span="16">
          <a-space>
            <span style="color: #666">批次：</span>
            <a-checkable-tag :checked="selectedBatch === null" @click="selectBatch(null)" style="cursor: pointer">
              全部
            </a-checkable-tag>
            <a-checkable-tag
              v-for="batch in batches"
              :key="batch.date"
              :checked="selectedBatch === batch.date"
              @click="selectBatch(batch.date)"
              style="cursor: pointer"
            >
              {{ formatDate(batch.date) }} ({{ batch.patient_count }}人)
            </a-checkable-tag>
          </a-space>
        </a-col>
        <a-col :span="8">
          <a-input-search v-model:value="searchText" placeholder="搜索病历号" allow-clear />
        </a-col>
      </a-row>
    </a-card>

    <!-- 数据表格 -->
    <a-card>
      <a-table
        :data-source="filteredRecords"
        :loading="loadingTree"
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
            <a-tag v-if="record.has_audio" color="green">有 ({{ record.segs?.length || 0 }}段)</a-tag>
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
            <a-button size="small" type="link" @click.stop="openDetail(record)">详情</a-button>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 详情抽屉 -->
    <a-drawer
      :open="drawerOpen"
      title="检查详情"
      placement="right"
      width="700px"
      @close="closeDrawer"
    >
      <template v-if="selectedRecord">
        <a-descriptions :column="2" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="病历号">{{ selectedRecord.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ formatDate(selectedRecord.date) }}</a-descriptions-item>
          <a-descriptions-item label="录音分段">{{ selectedRecord.segs?.length || 0 }} 段</a-descriptions-item>
          <a-descriptions-item label="B超结果">
            <a-tag v-if="selectedRecord.result" color="green">有</a-tag>
            <a-tag v-else color="default">无</a-tag>
          </a-descriptions-item>
        </a-descriptions>

        <a-card v-if="selectedRecord.segs?.length" size="small" style="margin-bottom: 16px">
          <template #title>录音播放 ({{ selectedRecord.segs.length }}段)</template>
          <AudioPlayer :segs="selectedRecord.segs" />
        </a-card>

        <!-- B 超结果 - 左右并行可编辑 -->
        <template v-if="selectedRecord.result">
          <a-divider>B 超检查结果
            <a-button v-if="!isEditingResult" size="small" type="link" @click="startEdit">编辑</a-button>
            <span v-else>
              <a-button size="small" type="link" @click="handleSaveResult" :loading="editSaving">保存</a-button>
              <a-button size="small" @click="cancelEdit">取消</a-button>
            </span>
          </a-divider>

          <a-row :gutter="16">
            <a-col :span="12">
              <a-card size="small" title="右侧卵泡" style="margin-bottom: 16px">
                <div v-if="isEditingResult">
                  <div v-for="(f, idx) in editForm.right_follicles" :key="'r'+idx" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center">
                    <a-input-number v-model:value="f.size" :min="0" :step="0.1" style="width: 100px" placeholder="尺寸" />
                    <span>×</span>
                    <a-input-number v-model:value="f.count" :min="1" :step="1" style="width: 60px" placeholder="数量" />
                    <a-button size="small" danger @click="editForm.right_follicles.splice(idx, 1)">×</a-button>
                  </div>
                  <a-button size="small" type="dashed" @click="editForm.right_follicles.push({size: 0, count: 1})">+ 添加</a-button>
                  <div style="margin-top: 8px; color: #666">合计: {{ editForm.right_follicles.reduce((s,f) => s + f.count, 0) }} 个</div>
                </div>
                <div v-else>
                  <div v-if="selectedRecord.result.right_follicle_total > 0">
                    <div style="font-size: 24px; font-weight: bold">{{ selectedRecord.result.right_follicle_total }} 个</div>
                    <div style="color: #666; font-size: 12px">{{ formatFollicles(selectedRecord.result.right_follicles) }}</div>
                  </div>
                  <div v-else style="color: #999">-</div>
                </div>
              </a-card>
            </a-col>

            <a-col :span="12">
              <a-card size="small" title="左侧卵泡" style="margin-bottom: 16px">
                <div v-if="isEditingResult">
                  <div v-for="(f, idx) in editForm.left_follicles" :key="'l'+idx" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center">
                    <a-input-number v-model:value="f.size" :min="0" :step="0.1" style="width: 100px" placeholder="尺寸" />
                    <span>×</span>
                    <a-input-number v-model:value="f.count" :min="1" :step="1" style="width: 60px" placeholder="数量" />
                    <a-button size="small" danger @click="editForm.left_follicles.splice(idx, 1)">×</a-button>
                  </div>
                  <a-button size="small" type="dashed" @click="editForm.left_follicles.push({size: 0, count: 1})">+ 添加</a-button>
                  <div style="margin-top: 8px; color: #666">合计: {{ editForm.left_follicles.reduce((s,f) => s + f.count, 0) }} 个</div>
                </div>
                <div v-else>
                  <div v-if="selectedRecord.result.left_follicle_total > 0">
                    <div style="font-size: 24px; font-weight: bold">{{ selectedRecord.result.left_follicle_total }} 个</div>
                    <div style="color: #666; font-size: 12px">{{ formatFollicles(selectedRecord.result.left_follicles) }}</div>
                  </div>
                  <div v-else style="color: #999">-</div>
                </div>
              </a-card>
            </a-col>
          </a-row>

          <a-row :gutter="16">
            <a-col :span="8">
              <div style="margin-bottom: 8px">
                <div style="color: #666; font-size: 12px">内膜厚度</div>
                <a-input-number v-if="isEditingResult" v-model:value="editForm.endometrium_thickness" :min="0" :step="0.1" style="width: 100%" suffix="mm" />
                <div v-else style="font-size: 16px">{{ selectedRecord.result.endometrium_thickness != null ? selectedRecord.result.endometrium_thickness + ' mm' : '-' }}</div>
              </div>
            </a-col>
            <a-col :span="8">
              <div style="margin-bottom: 8px">
                <div style="color: #666; font-size: 12px">内膜类型</div>
                <a-select v-if="isEditingResult" v-model:value="editForm.endometrium_type" allow-clear style="width: 100%">
                  <a-select-option value="A">A</a-select-option>
                  <a-select-option value="B">B</a-select-option>
                  <a-select-option value="C">C</a-select-option>
                  <a-select-option value="A-B">A-B</a-select-option>
                </a-select>
                <div v-else style="font-size: 16px">{{ selectedRecord.result.endometrium_type || '-' }}</div>
              </div>
            </a-col>
            <a-col :span="8">
              <div style="margin-bottom: 8px">
                <div style="color: #666; font-size: 12px">备注</div>
                <a-input v-if="isEditingResult" v-model:value="editForm.remark" size="small" />
                <div v-else style="font-size: 16px">{{ selectedRecord.result.remark || '-' }}</div>
              </div>
            </a-col>
          </a-row>

          <a-row :gutter="16" style="margin-top: 8px">
            <a-col :span="12">
              <div style="margin-bottom: 8px">
                <div style="color: #666; font-size: 12px">右卵巢</div>
                <a-input-group v-if="isEditingResult" compact>
                  <a-input-number v-model:value="editForm.right_ovary_length" :min="0" :step="0.1" placeholder="长" style="width: 45%" />
                  <span style="line-height: 32px"> × </span>
                  <a-input-number v-model:value="editForm.right_ovary_width" :min="0" :step="0.1" placeholder="宽" style="width: 45%" />
                </a-input-group>
                <div v-else style="font-size: 16px">
                  {{ selectedRecord.result.right_ovary_length && selectedRecord.result.right_ovary_width ? `${selectedRecord.result.right_ovary_length} × ${selectedRecord.result.right_ovary_width} mm` : '-' }}
                </div>
              </div>
            </a-col>
            <a-col :span="12">
              <div style="margin-bottom: 8px">
                <div style="color: #666; font-size: 12px">左卵巢</div>
                <a-input-group v-if="isEditingResult" compact>
                  <a-input-number v-model:value="editForm.left_ovary_length" :min="0" :step="0.1" placeholder="长" style="width: 45%" />
                  <span style="line-height: 32px"> × </span>
                  <a-input-number v-model:value="editForm.left_ovary_width" :min="0" :step="0.1" placeholder="宽" style="width: 45%" />
                </a-input-group>
                <div v-else style="font-size: 16px">
                  {{ selectedRecord.result.left_ovary_length && selectedRecord.result.left_ovary_width ? `${selectedRecord.result.left_ovary_length} × ${selectedRecord.result.left_ovary_width} mm` : '-' }}
                </div>
              </div>
            </a-col>
          </a-row>
        </template>
      </template>
    </a-drawer>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
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

    const drawerOpen = computed(() => store.drawerOpen)
    const selectedRecord = computed(() => store.selectedRecord)
    const batches = computed(() => store.batches)
    const selectedBatch = computed(() => store.selectedBatch)
    const loadingTree = computed(() => store.loadingTree)
    const allRecords = computed(() => store.records)

    const filteredRecords = computed(() => {
      if (!searchText.value.trim()) return allRecords.value
      const q = searchText.value.trim().toLowerCase()
      return allRecords.value.filter((r) => r.record_id.toLowerCase().includes(q))
    })

    function selectBatch(date: string | null) {
      store.selectBatch(date)
    }

    function openDetail(record: PatientExamination) {
      store.openDrawer(record)
    }

    function closeDrawer() {
      store.closeDrawer()
    }

    function onRowClick(record: PatientExamination) {
      return {
        onClick: () => openDetail(record),
        style: { cursor: 'pointer' }
      }
    }

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

    onMounted(() => {
      store.fetchBatches()
      store.fetchRecords()
    })

    function formatDate(d: string): string {
      if (!d || d.length !== 8) return d
      return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
    }

    function formatFollicles(follicles: BUltraResult['right_follicles'] | BUltraResult['left_follicles']): string {
      if (!follicles || !Array.isArray(follicles) || follicles.length === 0) return '-'
      return follicles.map((f) => `${f.size}×${f.count}`).join('  ')
    }

    function startEdit() {
      if (!selectedRecord.value?.result) return
      const r = selectedRecord.value.result
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
        await store.fetchRecords()
      } catch {
        message.error('保存失败')
      } finally {
        editSaving.value = false
      }
    }

    return {
      searchText, drawerOpen, selectedRecord, batches, selectedBatch, loadingTree,
      allRecords, filteredRecords, isEditingResult, editSaving, editForm,
      selectBatch, openDetail, closeDrawer, onRowClick, formatDate, formatFollicles,
      startEdit, cancelEdit, handleSaveResult,
    }
  },
})
</script>

<style scoped>
</style>
