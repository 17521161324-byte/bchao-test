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
    <a-drawer :open="drawerOpen" title="检查详情" placement="right" width="1200px" @close="closeDrawer">
      <template v-if="selectedRecord">
        <!-- 顶部描述区域 -->
        <a-descriptions :column="4" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="病历号">{{ selectedRecord.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ formatDate(selectedRecord.date) }}</a-descriptions-item>
          <a-descriptions-item label="录音分段">{{ selectedRecord.segs?.length || 0 }} 段</a-descriptions-item>
          <a-descriptions-item label="B超结果">
            <a-tag v-if="selectedRecord.result" color="green">有</a-tag>
            <a-tag v-else color="default">无</a-tag>
          </a-descriptions-item>
        </a-descriptions>

        <!-- ASR + LLM 并行双列布局 -->
        <a-row :gutter="16" style="margin-bottom: 16px">
          <!-- ============ 左列：ASR (多模型) ============ -->
          <a-col :span="12">
            <a-card size="small" style="margin-bottom: 16px; height: 100%">
              <template #title>
                <span>语音转写 (ASR)</span>
                <a-tag v-if="selectedAsrResult" color="blue" style="margin-left: 8px">{{ selectedAsrResult.model_name }}</a-tag>
              </template>
              <template #extra>
                <a-space :size="4">
                  <a-button type="primary" size="small" @click="runAsr" :loading="asrRunning">
                    <template #icon><ScanOutlined /></template>
                    {{ asrRunning ? '转写中...' : (currentAsrStatus === 'success' ? '重新识别' : '开始识别') }}
                  </a-button>
                  <span v-if="asrProgress" style="font-size: 12px; color: #666; margin-left: 8px">
                    处理中 {{ asrProgress.seg_index }} / {{ asrProgress.total }}
                  </span>
                </a-space>
              </template>

              <!-- ASR 模型选择 -->
              <div style="margin-bottom: 12px">
                <span style="font-size: 12px; color: #666; margin-right: 8px">模型:</span>
                <a-checkable-tag
                  v-for="m in asrModels"
                  :key="m.id"
                  :checked="asrModelId === m.id"
                  @click="asrModelId = m.id"
                  style="cursor: pointer; margin-right: 4px"
                  :color="getAsrModelStatusColor(m.id)"
                >
                  {{ m.name }}
                </a-checkable-tag>
              </div>

              <!-- 播放器 -->
              <AudioPlayer v-if="selectedRecord.segs?.length" :segs="selectedRecord.segs" style="margin-bottom: 12px" />

              <!-- ASR 结果 -->
              <div v-if="selectedAsrResult" style="max-height: 360px; overflow-y: auto">
                <div v-if="selectedAsrResult.status === 'failed'" style="color: #ff4d4f; margin-bottom: 8px; font-size: 12px">
                  转写失败: {{ selectedAsrResult.error_message || '未知错误' }}
                </div>
                <div style="font-size: 13px; color: #666; margin-bottom: 4px">转写结果：</div>
                <div style="background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 14px; line-height: 1.8; white-space: pre-wrap">{{ selectedAsrResult.full_transcript || '(无内容)' }}</div>
              </div>
              <a-empty v-else description="暂无转写结果" style="padding: 20px 0" />
            </a-card>
          </a-col>

          <!-- ============ 右列：LLM ============ -->
          <a-col :span="12">
            <a-card size="small" style="margin-bottom: 16px; height: 100%">
              <template #title>
                <span>LLM 结构化提取</span>
                <a-tag v-if="selectedAsrResult" color="blue" style="margin-left: 8px">ASR: {{ selectedAsrResult.model_name }}</a-tag>
                <a-tag v-if="llmResult" color="purple" style="margin-left: 8px">{{ llmResult.model_name }}</a-tag>
              </template>
              <template #extra>
                <a-space :size="4">
                  <a-select
                    v-model:value="selectedTemplateId"
                    placeholder="选择模版"
                    style="width: 140px"
                    size="small"
                    allow-clear
                    @change="onTemplateChange"
                  >
                    <a-select-option v-for="t in promptTemplates" :key="t.id" :value="t.id">{{ t.name }}</a-select-option>
                  </a-select>
                  <a-select v-model:value="llmModelId" style="width: 140px" size="small" placeholder="LLM模型" allow-clear>
                    <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
                  </a-select>
                  <a-button type="primary" size="small" @click="runLlm" :loading="llmRunning" :disabled="!selectedAsrResult">
                    <template #icon><RobotOutlined /></template>
                    {{ llmRunning ? '提取中...' : '开始提取' }}
                  </a-button>
                  <a-button type="link" size="small" @click="showTemplateModal = true">模版</a-button>
                </a-space>
              </template>

              <!-- LLM 结果 -->
              <div v-if="llmResult">
                <!-- A. 顶部: 模型信息 + 准确率 -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
                  <a-space>
                    <a-tag color="purple">{{ llmResult.model_name }}</a-tag>
                    <a-tag v-if="selectedAsrResult" color="blue">ASR: {{ selectedAsrResult.model_name }}</a-tag>
                  </a-space>
                  <a-button size="small" type="link" @click="showLlmDetailModal = true">查看完整 LLM 数据</a-button>
                </div>

                <!-- B. LLM 转写/总结内容 -->
                <a-card size="small">
                  <template #title><span style="font-size: 12px">LLM 转写/总结</span></template>
                  <div v-if="llmDisplayText" class="llm-summary-box">{{ llmDisplayText }}</div>
                  <a-empty v-else description="暂无 LLM 总结内容" style="padding: 12px 0" />
                </a-card>
              </div>
              <a-empty v-else description="请先完成 ASR 转写" style="padding: 20px 0" />
            </a-card>
          </a-col>
        </a-row>

        <!-- ==================== 卵泡明细 + B 超结果 并行显示 ==================== -->
        <a-divider>卵泡明细对比</a-divider>
        <a-row :gutter="16">
          <!-- LLM 卵泡结果 -->
          <a-col :span="12">
            <a-card size="small" title="LLM 提取结果" style="margin-bottom: 16px">
              <template #extra>
                <a-tag v-if="llmResult" color="purple">{{ llmResult.model_name }}</a-tag>
              </template>
              <div v-if="llmResult">
                <a-row :gutter="12" style="margin-bottom: 12px">
                  <a-col :span="12">
                    <a-card size="small" title="右侧卵泡" style="margin-bottom: 8px">
                      <div style="font-size: 22px; font-weight: bold">
                        {{ llmResult.structured?.right_follicle_total ?? '-' }}
                        <span style="font-size: 14px; font-weight: normal">个</span>
                        <CheckCircleOutlined v-if="compareField('right_follicle_total', true)" style="color: #52c41a; margin-left: 4px" />
                        <CloseCircleOutlined v-else-if="compareField('right_follicle_total', false)" style="color: #ff4d4f; margin-left: 4px" />
                      </div>
                      <div style="color: #666; font-size: 12px; margin-top: 4px">
                        {{ formatFollicles(llmResult.structured?.right_follicles) }}
                      </div>
                    </a-card>
                  </a-col>
                  <a-col :span="12">
                    <a-card size="small" title="左侧卵泡" style="margin-bottom: 8px">
                      <div style="font-size: 22px; font-weight: bold">
                        {{ llmResult.structured?.left_follicle_total ?? '-' }}
                        <span style="font-size: 14px; font-weight: normal">个</span>
                        <CheckCircleOutlined v-if="compareField('left_follicle_total', true)" style="color: #52c41a; margin-left: 4px" />
                        <CloseCircleOutlined v-else-if="compareField('left_follicle_total', false)" style="color: #ff4d4f; margin-left: 4px" />
                      </div>
                      <div style="color: #666; font-size: 12px; margin-top: 4px">
                        {{ formatFollicles(llmResult.structured?.left_follicles) }}
                      </div>
                    </a-card>
                  </a-col>
                </a-row>
                <a-descriptions :column="2" bordered size="small">
                  <a-descriptions-item label="内膜厚度">
                    <span :style="{ color: compareField('endometrium_thickness', true) ? '#52c41a' : (compareField('endometrium_thickness', false) ? '#ff4d4f' : 'inherit') }">
                      {{ llmResult.structured?.endometrium_thickness != null ? llmResult.structured.endometrium_thickness + ' mm' : '-' }}
                    </span>
                  </a-descriptions-item>
                  <a-descriptions-item label="内膜类型">
                    <span :style="{ color: compareField('endometrium_type', true) ? '#52c41a' : (compareField('endometrium_type', false) ? '#ff4d4f' : 'inherit') }">
                      {{ llmResult.structured?.endometrium_type || '-' }}
                    </span>
                  </a-descriptions-item>
                  <a-descriptions-item label="右卵巢">
                    {{ llmResult.structured?.right_ovary_length && llmResult.structured?.right_ovary_width ? `${llmResult.structured.right_ovary_length} × ${llmResult.structured.right_ovary_width} mm` : '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item label="左卵巢">
                    {{ llmResult.structured?.left_ovary_length && llmResult.structured?.left_ovary_width ? `${llmResult.structured.left_ovary_length} × ${llmResult.structured.left_ovary_width} mm` : '-' }}
                  </a-descriptions-item>
                  <a-descriptions-item label="备注" :span="2">
                    {{ llmResult.structured?.remark || '-' }}
                  </a-descriptions-item>
                </a-descriptions>
              </div>
              <a-empty v-else description="请先完成 LLM 提取" style="padding: 20px 0" />
            </a-card>
          </a-col>

          <!-- B 超真实结果 -->
          <a-col :span="12">
            <a-card size="small" title="B 超检查结果（真实值）" style="margin-bottom: 16px" v-if="selectedRecord.result">
              <a-row :gutter="12" style="margin-bottom: 12px">
                <a-col :span="12">
                  <a-card size="small" title="右侧卵泡" style="margin-bottom: 8px">
                    <div style="font-size: 22px; font-weight: bold">{{ selectedRecord.result.right_follicle_total }} 个</div>
                    <div style="color: #666; font-size: 12px; margin-top: 4px">{{ formatFollicles(selectedRecord.result.right_follicles) }}</div>
                  </a-card>
                </a-col>
                <a-col :span="12">
                  <a-card size="small" title="左侧卵泡" style="margin-bottom: 8px">
                    <div style="font-size: 22px; font-weight: bold">{{ selectedRecord.result.left_follicle_total }} 个</div>
                    <div style="color: #666; font-size: 12px; margin-top: 4px">{{ formatFollicles(selectedRecord.result.left_follicles) }}</div>
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
                <a-descriptions-item label="备注" :span="2" v-if="selectedRecord.result.remark">{{ selectedRecord.result.remark }}</a-descriptions-item>
              </a-descriptions>
            </a-card>
            <a-card v-else size="small" title="B 超检查结果" style="margin-bottom: 16px">
              <a-empty description="该检查记录无 B 超结果" style="padding: 20px 0" />
            </a-card>
          </a-col>
        </a-row>
      </template>
    </a-drawer>

    <!-- 提示词模版管理弹窗 -->
    <a-modal
      v-model:open="showTemplateModal"
      title="提示词模版管理"
      width="1000px"
      :footer="null"
      destroy-on-close
    >
      <a-row :gutter="16">
        <!-- 左侧:模版列表 -->
        <a-col :span="6">
          <a-button type="primary" size="small" style="margin-bottom: 12px" @click="createNewTemplate">
            <template #icon><PlusOutlined /></template>
            新增模版
          </a-button>
          <a-list
            :data-source="promptTemplates"
            :loading="templateLoading"
            size="small"
            bordered
            style="max-height: 560px; overflow-y: auto"
          >
            <template #renderItem="{ item }">
              <a-list-item
                :style="{ background: selectedTemplateId === item.id ? '#e6f7ff' : 'transparent', cursor: 'pointer' }"
                @click="selectTemplate(item.id)"
              >
                <a-list-item-meta>
                  <template #title>
                    <span>{{ item.name }}</span>
                    <a-tag v-if="item.is_default" color="gold" style="margin-left: 4px">默认</a-tag>
                  </template>
                  <template #description>
                    <div style="color: #999; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: pre-wrap; max-height: 40px">
                      {{ item.content }}
                    </div>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </a-col>

        <!-- 右侧:模版详情/编辑 + 预览 -->
        <a-col :span="18">
          <a-form layout="vertical" size="small">
            <a-form-item label="模版名称" required>
              <a-input v-model:value="templateForm.name" placeholder="如：B超提取模版 v2" />
            </a-form-item>
            <a-form-item>
              <a-switch v-model:checked="templateForm.is_default" checked-children="默认" un-checked-children="非默认" />
            </a-form-item>

            <a-tabs v-model:activeKey="templateTab" size="small">
              <a-tab-pane key="edit" tab="编辑">
                <a-textarea
                  v-model:value="templateForm.content"
                  :rows="18"
                  placeholder="# 角色...&#10;## 任务...&#10;{transcript}"
                  style="font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 13px"
                />
              </a-tab-pane>
              <a-tab-pane key="preview" tab="预览">
                <div class="markdown-preview" v-html="templatePreviewHtml"></div>
              </a-tab-pane>
            </a-tabs>

            <a-form-item style="margin-top: 12px">
              <a-space>
                <a-button type="primary" :loading="templateSaving" @click="saveTemplate">保存</a-button>
                <a-button :disabled="!templateForm.id" danger @click="deleteTemplate(templateForm.id)">删除</a-button>
                <a-button type="link" :disabled="!templateForm.content" @click="applyTemplateToCurrent">应用到当前检查</a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-col>
      </a-row>
    </a-modal>

    <!-- LLM 完整数据弹窗 -->
    <a-modal
      v-model:open="showLlmDetailModal"
      title="LLM 完整数据"
      width="900px"
      :footer="null"
    >
      <div v-if="currentLlmResult">
        <!-- 基本信息 -->
        <a-descriptions :column="3" bordered size="small" style="margin-bottom: 16px">
          <a-descriptions-item label="模型">{{ currentLlmResult.model_name }}</a-descriptions-item>
          <a-descriptions-item label="准确率">{{ currentLlmResult.accuracy != null ? (currentLlmResult.accuracy * 100).toFixed(0) + '%' : '-' }}</a-descriptions-item>
          <a-descriptions-item label="状态">{{ currentLlmResult.status }}</a-descriptions-item>
        </a-descriptions>

        <!--结构化结果 -->
        <a-card size="small" style="margin-bottom: 16px">
          <template #title><span style="font-size: 12px">结构化结果 (structured)</span></template>
          <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto">{{ JSON.stringify(currentLlmResult.structured || currentLlmResult.structured_result, null, 2) }}</pre>
        </a-card>

        <!-- summary / raw_output -->
        <a-card size="small" style="margin-bottom: 16px">
          <template #title><span style="font-size: 12px">总结/原始输出</span></template>
          <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 300px; overflow-y: auto">{{ currentLlmResult.summary_text || currentLlmResult.summary || currentLlmResult.raw_text || currentLlmResult.raw_output || '(空)' }}</pre>
        </a-card>

        <!-- 评估结果 -->
        <a-card size="small" v-if="currentLlmResult.evaluation">
          <template #title><span style="font-size: 12px">评估结果</span></template>
          <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto">{{ JSON.stringify(currentLlmResult.evaluation, null, 2) }}</pre>
        </a-card>
      </div>
    </a-modal>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  ScanOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined, PlusOutlined, EyeOutlined, EditOutlined,
} from '@ant-design/icons-vue'
import { useAppStore } from '@/stores'
import { resultApi, modelApi, testApi, promptTemplateApi, patientApi } from '@/api/client'
import type { PatientExamination, BUltraResult } from '@/types'
import AudioPlayer from '@/components/AudioPlayer/index.vue'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

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
    function openDetail(record: PatientExamination) {
  store.openDrawer(record)
}
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

    // --- ASR (持久化到后端, 多模型管理) ---
    const asrModels = ref<any[]>([])          // 所有 active ASR 模型
    const asrModelId = ref<number | undefined>(undefined)  // 当前选中的 ASR 模型
    const asrRunning = ref(false)
    const asrProgress = ref<{ seg_index: number; total: number } | null>(null)
    const asrPartialSegments = ref<Record<number, string>>({})
    // 当前检查记录的所有 ASR 结果 (按模型分组)
    const asrResultsAll = ref<any[]>([])
    // 当前选中的 ASR 结果 (用于展示 + LLM 输入)
    const selectedAsrResult = ref<any>(null)

    // 计算属性: 按 asr_model_id 分组, 每个模型取最新 success (或最新记录)
    const asrResultByModelId = computed(() => {
      const map: Record<number, any> = {}
      for (const r of asrResultsAll.value) {
        const mid = r.asr_model_id
        if (!map[mid]) {
          map[mid] = r
        } else {
          // 优先 success, 其次 created_at 更新
          const existing = map[mid]
          if (r.status === 'success' && existing.status !== 'success') {
            map[mid] = r
          } else if (r.status === existing.status) {
            // 同状态取更新的
            if (new Date(r.created_at) > new Date(existing.created_at)) {
              map[mid] = r
            }
          }
        }
      }
      return map
    })

    // 计算属性: 当前选中模型的转写状态
    const currentAsrStatus = computed(() => {
      if (!asrModelId.value) return 'idle'
      const r = asrResultByModelId.value[asrModelId.value]
      if (!r) return 'idle'
      return r.status  // success / running / failed
    })

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        // 只显示 active 模型
        asrModels.value = (asr as any[]).filter((m: any) => m.status === 'active')
        llmModels.value = (llm as any[]).filter((m: any) => m.status === 'active')
        if (llm.length > 0) {
          llmModelId.value = llm.find((m: any) => m.is_default)?.id || llm[0].id
        }
        // ASR 默认选中第一个 (后续根据当前结果调整)
        if (asrModels.value.length > 0 && !asrModelId.value) {
          asrModelId.value = asrModels.value[0].id
        }
      } catch (e) { console.error(e) }
    }

    // 加载当前检查记录的所有 ASR 结果
    async function loadAsrResults() {
      if (!selectedRecord.value) return
      const examRecordId = selectedRecord.value.id  // exam_record_id = patient_records.id
      try {
        const h = await patientApi.listAsrResults(examRecordId)
        asrResultsAll.value = h || []
      } catch { asrResultsAll.value = [] }

      // 自动选择最佳模型
      const map = asrResultByModelId.value
      // 优先 is_current + success
      let bestMid: number | undefined
      for (const mid of Object.keys(map)) {
        const r = map[mid]
        if (r.is_current && r.status === 'success') {
          bestMid = Number(mid)
          break
        }
      }
      // 其次第一个 success
      if (!bestMid) {
        for (const mid of Object.keys(map)) {
          if (map[mid].status === 'success') {
            bestMid = Number(mid)
            break
          }
        }
      }
      // 其次保持当前选择 (如果仍在 active 列表)
      if (!bestMid && asrModelId.value && asrModels.value.find(m => m.id === asrModelId.value)) {
        bestMid = asrModelId.value
      }
      // 否则第一个 active 模型
      if (!bestMid && asrModels.value.length > 0) {
        bestMid = asrModels.value[0].id
      }
      if (bestMid) asrModelId.value = bestMid

      // 更新当前展示结果
      updateSelectedAsrResult()
    }

    // 根据当前选中模型更新展示结果
    function updateSelectedAsrResult() {
      if (!asrModelId.value) {
        selectedAsrResult.value = null
        return
      }
      const r = asrResultByModelId.value[asrModelId.value]
      selectedAsrResult.value = r || null
    }

    async function runAsr() {
      if (!asrModelId.value || !selectedRecord.value) return
      const examRecordId = selectedRecord.value.id
      asrRunning.value = true
      asrProgress.value = null
      asrPartialSegments.value = {}
      try {
        const es = patientApi.runAsrSSE(examRecordId, asrModelId.value)
        es.addEventListener('progress', () => { /* total info */ })
        es.addEventListener('segment', () => {
          // 实时预览由 loadAsrResults 刷新
        })
        es.addEventListener('complete', async () => {
          asrProgress.value = null
          asrRunning.value = false
          es.close()
          // 从后端刷新正式结果
          await loadAsrResults()
        })
        es.addEventListener('error', () => {
          message.error('ASR 失败')
          asrProgress.value = null
          asrRunning.value = false
          es.close()
          // 刷新以显示失败状态
          loadAsrResults()
        })
      } catch (e) {
        message.error('ASR 启动失败')
        asrProgress.value = null
        asrRunning.value = false
      }
    }

    // --- LLM (持久化到后端, 基于当前选中的 ASR 结果) ---
    const llmModels = ref<any[]>([])
    const llmModelId = ref<number | undefined>(undefined)
    const llmRunning = ref(false)
    const currentLlmResult = ref<any>(null)
    const llmHistory = ref<any[]>([])
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

    async function loadCurrentLlmResult() {
      if (!selectedRecord.value) return
      const examRecordId = selectedRecord.value.id
      try {
        const res = await patientApi.getLlmCurrent(examRecordId)
        currentLlmResult.value = res || null
      } catch { currentLlmResult.value = null }
      try {
        const h = await patientApi.listLlmResults(examRecordId)
        llmHistory.value = h || []
      } catch { llmHistory.value = [] }
    }

    async function runLlm() {
      if (!selectedRecord.value) return
      if (!selectedAsrResult.value) {
        message.error('请先完成该检查记录的 ASR 转写')
        return
      }
      if (!llmModelId.value) {
        message.error('请选择 LLM 模型')
        return
      }
      const examRecordId = selectedRecord.value.id
      llmRunning.value = true
      try {
        const res = await patientApi.runLlm(examRecordId, {
          llm_model_id: llmModelId.value!,
          asr_result_id: selectedAsrResult.value?.id,
          prompt_content: llmPrompt.value,
        })
        await loadCurrentLlmResult()
        message.success('LLM 提取成功')
      } catch (e: any) {
        message.error(`LLM 提取失败: ${e?.response?.data?.detail || e?.message || ''}`)
      } finally {
        llmRunning.value = false
      }
    }

    // 获取 ASR 模型状态颜色
    function getAsrModelStatusColor(modelId: number): string {
      const r = asrResultByModelId.value[modelId]
      if (!r) return 'default'
      if (r.status === 'success') return 'blue'
      if (r.status === 'running') return 'orange'
      if (r.status === 'failed') return 'red'
      return 'default'
    }

    // ========== 提示词模版 ==========
    const promptTemplates = ref<any[]>([])
    const selectedTemplateId = ref<number | undefined>(undefined)
    const showTemplateModal = ref(false)
    const showLlmDetailModal = ref(false)
    const templateTab = ref<'edit' | 'preview'>('edit')
    const templateLoading = ref(false)
    const templateSaving = ref(false)
    const templateForm = reactive<{ id?: number; name: string; content: string; is_default: boolean }>({
      name: '',
      content: '',
      is_default: false,
    })

    // Markdown 预览
    const templatePreviewHtml = computed(() => md.render(templateForm.content || ''))

    // LLM 结构化结果兼容
    const structured = computed(() => currentLlmResult.value?.structured || currentLlmResult.value?.structured_result || {})

    // LLM 转写/总结内容
    const llmDisplayText = computed(() => {
      if (!currentLlmResult.value) return ''
      return (
        currentLlmResult.value.summary_text ||
        currentLlmResult.value.summary ||
        currentLlmResult.value.structured?.summary ||
        currentLlmResult.value.raw_text ||
        currentLlmResult.value.raw_output ||
        ''
      )
    })

    // Markdown 默认模版 (英文 JSON 键名, 与前端展示一致)
    const DEFAULT_TEMPLATE_CONTENT = `# 角色

你是一名辅助生殖 B 超检查信息结构化专家。

# 任务

请根据以下 ASR 转写文本,提取本次 B 超检查中的结构化字段,并以 JSON 格式返回。

# ASR 转写文本

{transcript}

# 输出要求

请只返回 JSON,不要返回其他任何解释文字。

# JSON 字段说明

- right_follicle_total: 右侧卵泡总数(整数)
- left_follicle_total: 左侧卵泡总数(整数)
- right_follicles: 右侧卵泡列表,每项为 {"size": 数值, "count": 整数}
- left_follicles: 左侧卵泡列表,每项为 {"size": 数值, "count": 整数}
- endometrium_thickness: 内膜厚度(数值,mm)
- endometrium_type: 内膜类型(A/B/C/A-B 等)
- right_ovary_length: 右卵巢长度(数值,mm)
- right_ovary_width: 右卵巢宽度(数值,mm)
- left_ovary_length: 左卵巢长度(数值,mm)
- left_ovary_width: 左卵巢宽度(数值,mm)
- remark: 备注/总结(文本)

# 返回格式示例

\`\`\`json
{
  "right_follicle_total": 10,
  "left_follicle_total": 6,
  "right_follicles": [
    {"size": 17.5, "count": 1},
    {"size": 15.0, "count": 1}
  ],
  "left_follicles": [
    {"size": 14.3, "count": 1}
  ],
  "endometrium_thickness": 11.7,
  "endometrium_type": "A",
  "right_ovary_length": 31,
  "right_ovary_width": 26,
  "left_ovary_length": 28,
  "left_ovary_width": 27,
  "remark": "未见明显异常"
}
\`\`\``

    async function loadTemplates() {
      templateLoading.value = true
      try {
        promptTemplates.value = await promptTemplateApi.list() as unknown as any[]
        if (promptTemplates.value.length === 0) {
          await promptTemplateApi.initDefaults()
          promptTemplates.value = await promptTemplateApi.list() as unknown as any[]
        }
        // 自动选择默认模版或第一条
        const defaultTmpl = promptTemplates.value.find((t: any) => t.is_default)
        const first = promptTemplates.value[0]
        const target = defaultTmpl ?? first
        if (target && !selectedTemplateId.value) {
          selectedTemplateId.value = target.id
          loadTemplateToForm(target)
        }
      } catch (e) {
        console.error('加载模版失败', e)
      } finally {
        templateLoading.value = false
      }
    }

    // 点击左侧模版,加载到右侧表单
    function selectTemplate(id: number) {
      selectedTemplateId.value = id
      const tmpl = promptTemplates.value.find((t: any) => t.id === id)
      if (tmpl) loadTemplateToForm(tmpl)
    }

    function loadTemplateToForm(record: any) {
      templateForm.id = record.id
      templateForm.name = record.name
      templateForm.content = record.content
      templateForm.is_default = record.is_default
    }

    function onTemplateChange(id: number | undefined) {
      if (!id) return
      const tmpl = promptTemplates.value.find((t: any) => t.id === id)
      if (tmpl) {
        llmPrompt.value = tmpl.content
        // 提示用户重新提取
        if (currentLlmResult.value && !llmRunning.value) {
          message.info('提示词已切换,请重新点击"开始提取"', 2)
        }
      }
    }

    function createNewTemplate() {
      templateForm.id = undefined
      templateForm.name = ''
      templateForm.content = DEFAULT_TEMPLATE_CONTENT
      templateForm.is_default = false
      selectedTemplateId.value = undefined
      templateTab.value = 'edit'
    }

    function resetTemplateForm() {
      if (templateForm.id) {
        const tmpl = promptTemplates.value.find((t: any) => t.id === templateForm.id)
        if (tmpl) loadTemplateToForm(tmpl)
      } else {
        createNewTemplate()
      }
    }

    // 应用到当前检查
    function applyTemplateToCurrent() {
      if (!templateForm.content?.trim()) {
        message.error('模版内容为空')
        return
      }
      llmPrompt.value = templateForm.content
      if (templateForm.id) selectedTemplateId.value = templateForm.id
      message.success('已应用到当前检查')
    }

    async function saveTemplate() {
      if (!templateForm.name?.trim() || !templateForm.content?.trim()) {
        message.error('请填写模版名称和内容')
        return
      }
      if (!templateForm.content.includes('{transcript}')) {
        message.error('模版内容必须包含 {transcript} 占位符')
        return
      }
      templateSaving.value = true
      try {
        if (templateForm.id) {
          await promptTemplateApi.update(templateForm.id, {
            name: templateForm.name,
            content: templateForm.content,
            is_default: templateForm.is_default,
          })
          message.success('更新成功')
        } else {
          const created = await promptTemplateApi.create({
            name: templateForm.name,
            content: templateForm.content,
            is_default: templateForm.is_default,
          })
          templateForm.id = created?.id
          message.success('创建成功')
        }
        await loadTemplates()
        // 保持当前编辑项选中
        if (templateForm.id) selectedTemplateId.value = templateForm.id
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '保存失败')
      } finally {
        templateSaving.value = false
      }
    }

    async function deleteTemplate(id: number | undefined) {
      if (!id) {
        message.error('请先选择模版')
        return
      }
      try {
        await promptTemplateApi.delete(id)
        message.success('删除成功')
        await loadTemplates()
        // 如果删除的是当前表单模版,重置表单
        if (templateForm.id === id) {
          createNewTemplate()
        }
      } catch {
        message.error('删除失败')
      }
    }

    function compareField(field: string, correct: boolean): boolean {
      if (!currentLlmResult.value?.structured || !selectedRecord.value?.result) return false
      const llmVal = (currentLlmResult.value.structured as any)[field]
      const gtVal = (selectedRecord.value.result as any)[field]
      if (llmVal == null || gtVal == null) return false
      const match = String(llmVal).trim() === String(gtVal).trim()
      return correct ? match : !match && llmVal !== undefined
    }

    function formatRawJson(llmResult: any): string {
      if (!llmResult) return ''
      const { model_name, structured, raw_text, accuracy } = llmResult
      const display: any = { model_name, accuracy, structured }
      if (raw_text) display.raw_text = raw_text
      return JSON.stringify(display, null, 2)
    }

    // 监听 drawer 中检查记录切换, 自动加载持久化结果 + 自动选中最佳模型
    watch(selectedRecord, async (rec) => {
      selectedAsrResult.value = null
      currentLlmResult.value = null
      asrResultsAll.value = []
      llmHistory.value = []
      llmModelId.value = undefined
      if (rec && drawerOpen.value) {
        await loadAsrResults()
        await loadCurrentLlmResult()
      }
    })

    // 监听 ASR 模型切换, 更新展示结果
    watch(asrModelId, () => {
      updateSelectedAsrResult()
    })

    onMounted(() => {
      loadModels()
      loadTemplates()
      store.fetchBatches()
      store.fetchRecords()
    })

    return {
      searchText, drawerOpen, selectedRecord, batches, selectedBatch, loadingTree,
      allRecords, filteredRecords,
      asrModels, asrModelId, asrRunning, asrProgress, runAsr,
      asrResultByModelId, currentAsrStatus, selectedAsrResult,
      llmModels, llmModelId, llmRunning, llmResult: currentLlmResult, llmPrompt, runLlm, compareField, formatRawJson,
      structured, llmDisplayText,
      selectBatch, openDetail, closeDrawer, onRowClick, formatDate, formatFollicles, getAsrModelStatusColor,
      ScanOutlined, RobotOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined, PlusOutlined, EyeOutlined, EditOutlined,
      promptTemplates, selectedTemplateId, showTemplateModal, showLlmDetailModal, templateTab,
      templateLoading, templateSaving, templateForm, templatePreviewHtml,
      selectTemplate, createNewTemplate, applyTemplateToCurrent, resetTemplateForm, saveTemplate, deleteTemplate,
      asrResultsAll, llmHistory,
    }
  },
})
</script>

<style scoped>
.markdown-preview {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 16px;
  min-height: 420px;
  max-height: 520px;
  overflow: auto;
  background: #fff;
  font-size: 13px;
  line-height: 1.7;
}
.markdown-preview h1 { font-size: 18px; font-weight: 600; margin: 16px 0 8px; border-bottom: 1px solid #eee; padding-bottom: 6px; }
.markdown-preview h2 { font-size: 16px; font-weight: 600; margin: 14px 0 8px; }
.markdown-preview h3 { font-size: 14px; font-weight: 600; margin: 12px 0 6px; }
.markdown-preview p { margin: 6px 0; }
.markdown-preview ul, .markdown-preview ol { padding-left: 24px; margin: 6px 0; }
.markdown-preview li { margin: 3px 0; }
.markdown-preview pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; margin: 8px 0; }
.markdown-preview code { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 12px; background: rgba(175,184,193,0.2); padding: 2px 4px; border-radius: 4px; }
.markdown-preview pre code { background: transparent; padding: 0; }
.markdown-preview blockquote { border-left: 4px solid #ddd; margin: 8px 0; padding: 4px 12px; color: #666; }
.llm-summary-box {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
  max-height: 240px;
  overflow-y: auto;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
}
</style>
