<template>
  <div class="page-container">
    <!-- 筛选区域 -->
    <a-card style="margin-bottom: 16px">
      <a-row :gutter="16" align="middle">
        <a-col :span="16">
          <a-space>
            <span style="color: #666">批次：</span>
            <a-checkable-tag :checked="selectedBatch === null" @click="selectBatch(null)" style="cursor: pointer">全部</a-checkable-tag>
            <a-checkable-tag v-for="batch in batches" :key="batch.date" :checked="selectedBatch === batch.date" @click="selectBatch(batch.date)" style="cursor: pointer">
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
      <a-table :data-source="filteredRecords" :loading="loadingTree" :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }" size="small" :custom-row="onRowClick" row-key="id">
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
    <a-drawer :open="drawerOpen" title="检查详情" placement="right" width="750px" @close="closeDrawer">
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

        <!-- ==================== ASR 区域 ==================== -->
        <a-card size="small" style="margin-bottom: 16px">
          <template #title>
            <span>语音转写 (ASR)</span>
            <a-tag v-if="asrResult" color="blue" style="margin-left: 8px">{{ asrResult.model_name }}</a-tag>
          </template>
          <template #extra>
            <a-select v-model:value="asrModelId" style="width: 180px" size="small" placeholder="选择ASR模型">
              <a-select-option v-for="m in asrModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
            </a-select>
            <a-button type="primary" size="small" @click="runAsr" :loading="asrRunning" style="margin-left: 8px">
              <template #icon><ScanOutlined /></template>
              {{ asrRunning ? '转写中...' : (asrResult ? '重新识别' : '开始识别') }}
            </a-button>
          </template>

          <!-- 播放器 -->
          <AudioPlayer v-if="selectedRecord.segs?.length" :segs="selectedRecord.segs" style="margin-bottom: 12px" />

          <!-- ASR 结果 -->
          <div v-if="asrResult">
            <div style="font-size: 13px; color: #666; margin-bottom: 4px">转写结果：</div>
            <div style="background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 14px; line-height: 1.8; white-space: pre-wrap">{{ asrResult.full_transcript || '(无内容)' }}</div>
          </div>
          <a-empty v-else description="暂无转写结果" :image="null" style="padding: 20px 0" />
        </a-card>

        <!-- ==================== LLM 区域 ==================== -->
        <a-card size="small" style="margin-bottom: 16px">
          <template #title>
            <span>LLM 结构化提取</span>
            <a-tag v-if="llmResult" color="purple" style="margin-left: 8px">{{ llmResult.model_name }}</a-tag>
          </template>
          <template #extra>
            <a-select v-model:value="llmModelId" style="width: 180px" size="small" placeholder="选择LLM模型" allow-clear>
              <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
            </a-select>
            <a-button type="primary" size="small" @click="runLlm" :loading="llmRunning" :disabled="!asrResult" style="margin-left: 8px">
              <template #icon><RobotOutlined /></template>
              {{ llmRunning ? '提取中...' : '开始提取' }}
            </a-button>
          </template>

          <!-- 提示词编辑 -->
          <div style="margin-bottom: 12px">
            <div style="margin-bottom: 4px; color: #666; font-size: 12px">提示词模板</div>
            <a-textarea v-model:value="llmPrompt" :rows="4" :disabled="!asrResult" placeholder="请先完成 ASR 转写" />
          </div>

          <!-- LLM 结果 -->
          <div v-if="llmResult">
            <a-row :gutter="16">
              <a-col :span="12">
                <div style="font-size: 12px; color: #666; margin-bottom: 4px">右侧卵泡</div>
                <div style="font-size: 20px; font-weight: bold">
                  {{ llmResult.structured?.right_follicle_total ?? '-' }}
                  <CheckCircleOutlined v-if="compareField('right_follicle_total', true)" style="color: #52c41a" />
                  <CloseCircleOutlined v-else-if="compareField('right_follicle_total', false)" style="color: #ff4d4f" />
                </div>
              </a-col>
              <a-col :span="12">
                <div style="font-size: 12px; color: #666; margin-bottom: 4px">左侧卵泡</div>
                <div style="font-size: 20px; font-weight: bold">
                  {{ llmResult.structured?.left_follicle_total ?? '-' }}
                  <CheckCircleOutlined v-if="compareField('left_follicle_total', true)" style="color: #52c41a" />
                  <CloseCircleOutlined v-else-if="compareField('left_follicle_total', false)" style="color: #ff4d4f" />
                </div>
              </a-col>
            </a-row>
            <a-row :gutter="16" style="margin-top: 8px">
              <a-col :span="8">
                <div style="font-size: 12px; color: #666">内膜厚度</div>
                <div style="font-size: 16px">
                  {{ llmResult.structured?.endometrium_thickness != null ? llmResult.structured.endometrium_thickness + ' mm' : '-' }}
                  <CheckCircleOutlined v-if="compareField('endometrium_thickness', true)" style="color: #52c41a" />
                  <CloseCircleOutlined v-else-if="compareField('endometrium_thickness', false)" style="color: #ff4d4f" />
                </div>
              </a-col>
              <a-col :span="8">
                <div style="font-size: 12px; color: #666">内膜类型</div>
                <div style="font-size: 16px">
                  {{ llmResult.structured?.endometrium_type || '-' }}
                  <CheckCircleOutlined v-if="compareField('endometrium_type', true)" style="color: #52c41a" />
                  <CloseCircleOutlined v-else-if="compareField('endometrium_type', false)" style="color: #ff4d4f" />
                </div>
              </a-col>
              <a-col :span="8">
                <div style="font-size: 12px; color: #666">准确率</div>
                <div style="font-size: 16px; font-weight: bold; color: #1677ff">{{ llmResult.accuracy != null ? (llmResult.accuracy * 100).toFixed(0) + '%' : '-' }}</div>
              </a-col>
            </a-row>
          </div>
          <a-empty v-else description="请先完成 ASR 转写" :image="null" style="padding: 20px 0" />
        </a-card>

        <!-- ==================== B 超结果 ==================== -->
        <template v-if="selectedRecord.result">
          <a-divider>B 超检查结果（真实值）</a-divider>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-card size="small" title="右侧卵泡" style="margin-bottom: 16px">
                <div style="font-size: 24px; font-weight: bold">{{ selectedRecord.result.right_follicle_total }} 个</div>
                <div style="color: #666; font-size: 12px">{{ formatFollicles(selectedRecord.result.right_follicles) }}</div>
              </a-card>
            </a-col>
            <a-col :span="12">
              <a-card size="small" title="左侧卵泡" style="margin-bottom: 16px">
                <div style="font-size: 24px; font-weight: bold">{{ selectedRecord.result.left_follicle_total }} 个</div>
                <div style="color: #666; font-size: 12px">{{ formatFollicles(selectedRecord.result.left_follicles) }}</div>
              </a-card>
            </a-col>
          </a-row>
          <a-descriptions :column="2" bordered size="small">
            <a-descriptions-item label="内膜厚度">
              {{ selectedRecord.result.endometrium_thickness != null ? selectedRecord.result.endometrium_thickness + ' mm' : '-' }}
            </a-descriptions-item>
            <a-descriptions-item label="内膜类型">{{ selectedRecord.result.endometrium_type || '-' }}</a-descriptions-item>
            <a-descriptions-item label="右卵巢">
              {{ selectedRecord.result.right_ovary_length && selectedRecord.result.right_ovary_width ? `${selectedRecord.result.right_ovary_length} × ${selectedRecord.result.right_ovary_width} mm` : '-' }}
            </a-descriptions-item>
            <a-descriptions-item label="左卵巢">
              {{ selectedRecord.result.left_ovary_length && selectedRecord.result.left_ovary_width ? `${selectedRecord.result.left_ovary_length} × ${selectedRecord.result.left_ovary_width} mm` : '-' }}
            </a-descriptions-item>
            <a-descriptions-item label="备注" :span="2">{{ selectedRecord.result.remark || '-' }}</a-descriptions-item>
          </a-descriptions>
        </template>
      </template>
    </a-drawer>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { ScanOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { useAppStore } from '@/stores'
import { resultApi, modelApi, testApi } from '@/api/client'
import type { PatientExamination, BUltraResult } from '@/types'
import AudioPlayer from '@/components/AudioPlayer/index.vue'

export default defineComponent({
  name: 'DataImport',
  components: { AudioPlayer },
  setup() {
    const store = useAppStore()
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

    function selectBatch(date: string | null) { store.selectBatch(date) }
    function openDetail(record: PatientExamination) { store.openDrawer(record) }
    function closeDrawer() { store.closeDrawer() }
    function onRowClick(record: PatientExamination) {
      return { onClick: () => openDetail(record), style: { cursor: 'pointer' } }
    }

    onMounted(() => { store.fetchBatches(); store.fetchRecords() })

    function formatDate(d: string): string {
      if (!d || d.length !== 8) return d
      return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`
    }
    function formatFollicles(follicles: BUltraResult['right_follicles'] | BUltraResult['left_follicles']): string {
      if (!follicles || !Array.isArray(follicles) || follicles.length === 0) return '-'
      return follicles.map((f) => `${f.size}×${f.count}`).join('  ')
    }

    // --- ASR ---
    const asrModels = ref<any[]>([])
    const asrModelId = ref<number | undefined>(undefined)
    const asrRunning = ref(false)
    const asrResult = ref<any>(null)

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        asrModels.value = asr as any[]
        llmModels.value = llm as any[]
        if (asr.length > 0) asrModelId.value = asr[0].id
      } catch (e) { console.error(e) }
    }

    async function runAsr() {
      if (!asrModelId.value || !selectedRecord.value) return
      asrRunning.value = true
      try {
        const res = await testApi.runAsr(selectedRecord.value.record_id, asrModelId.value)
        asrResult.value = res
      } catch { message.error('ASR 失败') }
      finally { asrRunning.value = false }
    }

    // --- LLM ---
    const llmModels = ref<any[]>([])
    const llmModelId = ref<number | undefined>(undefined)
    const llmRunning = ref(false)
    const llmResult = ref<any>(null)
    const llmPrompt = ref(`你是一名辅助生殖超声检查专家。请从以下 B 超检查的语音转写文本中提取关键信息，并以 JSON 格式返回。

## 需要提取的字段

- right_follicle_total: 右侧卵泡总数（整数）
- left_follicle_total: 左侧卵泡总数（整数）
- endometrium_thickness: 内膜厚度（mm，数值）
- endometrium_type: 内膜类型（A/B/C/A-B 等）
- right_ovary_length: 右卵巢长度（mm）
- right_ovary_width: 右卵巢宽度（mm）
- left_ovary_length: 左卵巢长度（mm）
- left_ovary_width: 左卵巢宽度（mm）
- summary: 自然语言总结

## 转写文本

{transcript}

## 返回格式

请只返回 JSON，不要有其他内容：
{
  "right_follicle_total": 0,
  "left_follicle_total": 0,
  "endometrium_thickness": 0,
  "endometrium_type": "",
  "right_ovary_length": 0,
  "right_ovary_width": 0,
  "left_ovary_length": 0,
  "left_ovary_width": 0,
  "summary": ""
}`)

    async function runLlm() {
      if (!asrResult.value) return
      llmRunning.value = true
      try {
        const res = await testApi.runLlm({
          transcript: asrResult.value.full_transcript,
          llm_model_id: llmModelId.value,
          prompt_template: llmPrompt.value,
        })
        llmResult.value = res
      } catch { message.error('LLM 提取失败') }
      finally { llmRunning.value = false }
    }

    function compareField(field: string, correct: boolean): boolean {
      if (!llmResult.value?.structured || !selectedRecord.value?.result) return false
      const llmVal = llmResult.value.structured[field]
      const gtVal = selectedRecord.value.result[field]
      if (llmVal == null || gtVal == null) return false
      const match = String(llmVal).trim() === String(gtVal).trim()
      return correct ? match : !match && llmVal !== undefined
    }

    onMounted(() => { loadModels() })

    return {
      searchText, drawerOpen, selectedRecord, batches, selectedBatch, loadingTree,
      allRecords, filteredRecords, asrModels, asrModelId, asrRunning, asrResult, runAsr,
      llmModels, llmModelId, llmRunning, llmResult, llmPrompt, runLlm, compareField,
      selectBatch, openDetail, closeDrawer, onRowClick, formatDate, formatFollicles,
      ScanOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined,
    }
  },
})
</script>

<style scoped>
</style>
