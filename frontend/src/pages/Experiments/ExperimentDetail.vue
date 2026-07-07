<template>
  <div class="page-container">
    <div class="page-header">
      <h2>实验详情 - {{ batch?.name || '' }}</h2>
      <a-space>
        <router-link to="/experiments"><a-button><ArrowLeftOutlined />返回列表</a-button></router-link>
        <a-button @click="fetchData"><ReloadOutlined />刷新</a-button>
      </a-space>
    </div>

    <!-- 实验关联信息 -->
    <a-card size="small" style="margin-bottom: 16px" v-if="batch">
      <a-descriptions :column="4" bordered size="small">
        <a-descriptions-item label="实验名称">{{ batch.name }}</a-descriptions-item>
        <a-descriptions-item label="状态">
          <a-tag :color="batch.status === 'completed' ? 'green' : batch.status === 'running' ? 'blue' : 'default'">
            {{ batch.status }}
          </a-tag>
        </a-descriptions-item>
        <a-descriptions-item label="患者数">{{ (batch.selected_patient_ids || []).length }}人</a-descriptions-item>
        <a-descriptions-item label="总任务">{{ batch.total_tasks }}</a-descriptions-item>
        <a-descriptions-item label="ASR模型" :span="2">
          {{ batch.combinations?.map((c: any) => get_model_name(c.asr_model_id)).filter(Boolean).join(', ') || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="LLM模型" :span="2">
          {{ batch.combinations?.map((c: any) => get_model_name(c.llm_model_id)).filter(Boolean).join(', ') || '-' }}
        </a-descriptions-item>
        <a-descriptions-item label="提示词模板" :span="4">
          {{ batch.combinations?.map((c: any) => c.prompt_name).filter(Boolean).join(', ') || '-' }}
        </a-descriptions-item>
      </a-descriptions>
    </a-card>

    <!-- 进度条 -->
    <a-card v-if="batch && (batch.status === 'running' || batch.status === 'partial')" style="margin-bottom: 16px">
      <a-row :gutter="16" align="middle">
        <a-col :span="6"><a-statistic title="总任务" :value="progress?.total || 0" /></a-col>
        <a-col :span="6"><a-statistic title="成功" :value="progress?.success || 0" :value-style="{ color: '#52c41a' }" /></a-col>
        <a-col :span="6"><a-statistic title="失败" :value="progress?.failed || 0" :value-style="{ color: '#ff4d4f' }" /></a-col>
        <a-col :span="6"><a-statistic title="进行中" :value="progress?.running || 0" :value-style="{ color: '#1890ff' }" /></a-col>
      </a-row>
      <a-progress
        :percent="progress ? Math.round(((progress.success + progress.failed) / Math.max(progress.total, 1)) * 100) : 0"
        :status="batch.status === 'running' ? 'active' : 'normal'"
        :format="() => `${progress ? progress.success + progress.failed : 0}/${progress?.total || 0}`"
        style="margin-top: 12px"
      />
    </a-card>

    <!-- 控制按钮 -->
    <a-space style="margin-bottom: 16px">
      <a-button type="primary" @click="handleStart" :disabled="batch?.status === 'running' || !batch?.combinations?.length">开始实验</a-button>
      <a-button @click="handlePause" v-if="batch?.status === 'running'">暂停</a-button>
      <a-button @click="handleResume" v-if="batch?.status === 'paused'">继续</a-button>
      <a-button @click="handleRetryFailed" v-if="batch?.failure_count > 0">重试失败</a-button>
    </a-space>

    <!-- 实验组合管理 -->
    <a-card size="small" style="margin-bottom: 16px">
      <template #title>
        <a-space>
          <span>实验组合 ({{ batch?.combinations?.length || 0 }})</span>
          <a-button size="small" type="primary" @click="showComboModal">+ 添加组合</a-button>
        </a-space>
      </template>
      <a-row :gutter="8" v-if="batch?.combinations?.length">
        <a-col v-for="combo in batch.combinations" :key="combo.id" :span="8">
          <a-tag color="blue" style="margin-bottom: 4px">
            {{ get_model_name(combo.asr_model_id) }}{{ combo.llm_model_id ? ' + ' + get_model_name(combo.llm_model_id) : '' }}
            <span v-if="combo.prompt_name"> | 模板:{{ combo.prompt_name }}</span>
          </a-tag>
        </a-col>
      </a-row>
      <a-empty v-else description="暂无组合，请点击上方按钮添加" style="padding: 12px 0" />
    </a-card>

    <!-- 筛选 -->
    <a-card size="small" style="margin-bottom: 16px">
      <a-space>
        <span>显示：</span>
        <a-radio-group v-model:value="filter" button-style="solid" size="small">
          <a-radio-button value="all">全部</a-radio-button>
          <a-radio-button value="with_result">有LLM结果</a-radio-button>
          <a-radio-button value="mismatch">有差异</a-radio-button>
        </a-radio-group>
      </a-space>
    </a-card>

    <!-- 患者结果对比表格 -->
    <a-card title="患者结果对比" v-if="batch && batch.selected_patient_ids && batch.selected_patient_ids.length > 0">
      <a-table
        v-if="filteredTasks.length > 0"
        :data-source="filteredTasks"
        :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        size="small"
        :row-key="(row: any) => row.task ? `${row.task.id}-${row.task.patient_id}` : `pending-${row.record_id}-${row.date}`"
        :scroll="{ x: 1800 }"
      >
        <a-table-column title="病历号" data-index="record_id" :width="100" fixed="left" />
        <a-table-column title="日期" data-index="date" :width="100" />
        <a-table-column title="状态" :width="100">
          <template #default="{ record }">
            <a-tag :color="record.status === 'success' ? 'green' : record.status === 'failed' ? 'red' : record.status === 'running' ? 'blue' : 'default'">
              {{ record.status }}
            </a-tag>
            <a-tooltip v-if="record.error_message" :title="record.error_message">
              <span style="color: #ff4d4f; margin-left: 4px">⚠</span>
            </a-tooltip>
          </template>
        </a-table-column>

        <!-- ASR 转写结果 -->
        <a-table-column title="ASR转写" :width="200">
          <template #default="{ record }">
            <div style="max-height: 60px; overflow-y: auto; font-size: 12px; white-space: pre-wrap">
              {{ record.full_transcript || '-' }}
            </div>
          </template>
        </a-table-column>

        <!-- 右侧卵泡 -->
        <a-table-column title="右卵泡" :width="120">
          <template #default="{ record }">
            <div style="cursor:pointer" @click="openFieldModal(record.task, 'right_follicle_total')">
              <div>金标: {{ record.gt_right ?? '-' }}</div>
              <div :style="{ color: record.gt_right !== record.llm_right ? '#ff4d4f' : '#52c41a' }">
                LLM: {{ record.llm_right ?? '-' }}
              </div>
            </div>
          </template>
        </a-table-column>

        <!-- 左侧卵泡 -->
        <a-table-column title="左卵泡" :width="120">
          <template #default="{ record }">
            <div style="cursor:pointer" @click="openFieldModal(record.task, 'left_follicle_total')">
              <div>金标: {{ record.gt_left ?? '-' }}</div>
              <div :style="{ color: record.gt_left !== record.llm_left ? '#ff4d4f' : '#52c41a' }">
                LLM: {{ record.llm_left ?? '-' }}
              </div>
            </div>
          </template>
        </a-table-column>

        <!-- 内膜厚度 -->
        <a-table-column title="内膜厚度" :width="100">
          <template #default="{ record }">
            <div style="cursor:pointer" @click="openFieldModal(record.task, 'endometrium_thickness')">
              <div>金标: {{ record.gt_endo_thick ?? '-' }}</div>
              <div :style="{ color: record.gt_endo_thick !== record.llm_endo_thick ? '#ff4d4f' : '#52c41a' }">
                LLM: {{ record.llm_endo_thick ?? '-' }}
              </div>
            </div>
          </template>
        </a-table-column>

        <!-- 内膜类型 -->
        <a-table-column title="内膜类型" :width="80">
          <template #default="{ record }">
            <div style="cursor:pointer" @click="openFieldModal(record.task, 'endometrium_type')">
              <div>金标: {{ record.gt_endo_type ?? '-' }}</div>
              <div :style="{ color: record.gt_endo_type !== record.llm_endo_type ? '#ff4d4f' : '#52c41a' }">
                LLM: {{ record.llm_endo_type ?? '-' }}
              </div>
            </div>
          </template>
        </a-table-column>

        <!-- 右卵巢 -->
        <a-table-column title="右卵巢" :width="100">
          <template #default="{ record }">
            <div style="cursor:pointer" @click="openFieldModal(record.task, 'right_ovary_length')">
              <div>金标: {{ record.gt_r_ovary }}</div>
              <div :style="{ color: record.gt_r_ovary !== record.llm_r_ovary ? '#ff4d4f' : '#52c41a' }">
                LLM: {{ record.llm_r_ovary }}
              </div>
            </div>
          </template>
        </a-table-column>

        <!-- 左卵巢 -->
        <a-table-column title="左卵巢" :width="100">
          <template #default="{ record }">
            <div style="cursor:pointer" @click="openFieldModal(record.task, 'left_ovary_length')">
              <div>金标: {{ record.gt_l_ovary }}</div>
              <div :style="{ color: record.gt_l_ovary !== record.llm_l_ovary ? '#ff4d4f' : '#52c41a' }">
                LLM: {{ record.llm_l_ovary }}
              </div>
            </div>
          </template>
        </a-table-column>

        <!-- 备注 -->
        <a-table-column title="备注" :width="120">
          <template #default="{ record }">
            <div style="cursor:pointer" @click="openFieldModal(record.task, 'remark')">
              <div>金标: {{ record.gt_remark || '-' }}</div>
              <div :style="{ color: record.gt_remark !== record.llm_remark ? '#ff4d4f' : '#52c41a' }">
                LLM: {{ record.llm_remark || '-' }}
              </div>
            </div>
          </template>
        </a-table-column>

        <a-table-column title="耗时" :width="80">
          <template #default="{ record }">{{ record.total_duration?.toFixed(1) || '-' }}s</template>
        </a-table-column>
      </a-table>
      <a-empty v-if="filteredTasks.length === 0" description="暂无患者数据" style="padding: 20px 0" />
    </a-card>

    <!-- 添加组合弹窗 -->
    <a-modal
      v-model:open="comboModalOpen"
      title="添加实验组合"
      :confirm-loading="comboCreating"
      @ok="handleAddCombo"
      :width="600"
    >
      <a-form layout="vertical" size="small">
        <a-form-item label="ASR 模型" required>
          <a-select v-model:value="comboForm.asr_model_id" placeholder="选择 ASR 模型" show-search>
            <a-select-option v-for="m in asrModels" :key="m.id" :value="m.id">
              {{ m.name }} ({{ m.provider }})
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="LLM 模型">
          <a-select v-model:value="comboForm.llm_model_id" placeholder="不使用 LLM" allow-clear show-search>
            <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">
              {{ m.name }} ({{ m.provider }})
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="提示词模板">
          <a-select
            v-model:value="comboForm.prompt_name"
            placeholder="选择模板（可选）"
            allow-clear
            show-search
            @change="onPromptTemplateChange"
          >
            <a-select-option v-for="t in promptTemplates" :key="t.name" :value="t.name">
              {{ t.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="提示词内容">
          <a-textarea
            v-model:value="comboForm.prompt_template"
            :rows="6"
            placeholder="含 {transcript} 占位符的模板（可选）"
          />
        </a-form-item>
        <a-form-item label="热词（每行一个）">
          <a-textarea v-model:value="hotwordsRaw" :rows="3" placeholder="术后&#10;监测&#10;..." />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 字段对比弹窗 -->
    <FieldCompareModal :modal="fieldModal" @close="closeFieldModal" />
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { experimentApi } from '@/api/experiment'
import { audioApi, modelApi } from '@/api/client'
import { promptApi } from '@/api/prompt'
import { useFieldCompare } from '@/composables/useFieldCompare'
import FieldCompareModal from '@/components/FieldCompareModal/index.vue'

export default defineComponent({
  name: 'ExperimentDetail',
  components: { FieldCompareModal },
  setup() {
    const route = useRoute()
    const batchId = computed(() => Number(route.params.id))
    const batch = ref<any>(null)
    const tasks = ref<any[]>([])
    const filter = ref('all')
    const modelsMap = ref<Record<number, string>>({})
    const progress = ref<any>(null)

    // 字段对比
    const { fieldModal, openFieldModal, closeFieldModal } = useFieldCompare()

    // 组合配置
    const asrModels = ref<any[]>([])
    const llmModels = ref<any[]>([])
    const promptTemplates = ref<any[]>([])
    const comboModalOpen = ref(false)
    const comboCreating = ref(false)
    const hotwordsRaw = ref('')
    const comboForm = reactive({
      asr_model_id: null as number | null,
      llm_model_id: null as number | null,
      prompt_name: '',
      prompt_template: '',
    })

    function get_model_name(id: number): string {
      return modelsMap.value[id] || `#${id}`
    }

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        const map: Record<number, string> = {}
        for (const m of [...asr, ...llm]) map[m.id] = m.name
        modelsMap.value = map
        asrModels.value = asr
        llmModels.value = llm
      } catch { /* ignore */ }
    }

    async function loadPromptTemplates() {
      try {
        const res = await promptApi.list()
        promptTemplates.value = res.data || []
      } catch { /* ignore */ }
    }

    function onPromptTemplateChange(name: string) {
      const tmpl = promptTemplates.value.find((t: any) => t.name === name)
      if (tmpl) comboForm.prompt_template = tmpl.content
    }

    function showComboModal() {
      comboForm.asr_model_id = null
      comboForm.llm_model_id = null
      comboForm.prompt_name = ''
      comboForm.prompt_template = ''
      hotwordsRaw.value = ''
      loadModels()
      loadPromptTemplates()
      comboModalOpen.value = true
    }

    async function handleAddCombo() {
      if (!comboForm.asr_model_id) {
        message.error('请选择 ASR 模型')
        return
      }
      comboCreating.value = true
      try {
        await experimentApi.addCombination(batchId.value, {
          ...comboForm,
          hotwords: hotwordsRaw.value.split('\n').map((s: string) => s.trim()).filter(Boolean),
        })
        message.success('已添加组合')
        comboModalOpen.value = false
        fetchData()
      } catch {
        message.error('添加失败')
      } finally {
        comboCreating.value = false
      }
    }

    async function fetchProgress() {
      try {
        const res = await experimentApi.progress(batchId.value)
        progress.value = res
      } catch { /* ignore */ }
    }

    async function fetchData() {
      try {
        const res = await experimentApi.get(batchId.value)
        // 确保 batch.value 是数据对象，而不是响应对象
        batch.value = res.data || res
        fetchProgress()
      } catch {
        message.error('加载失败')
      }
    }

    async function fetchTasks() {
      try {
        const res = await experimentApi.tasks(batchId.value)
        tasks.value = res
      } catch { /* ignore */ }
    }

    // fetchGroundTruths / fetchPatientsInfo 已不需要 (后端 /{batch_id}/tasks 已返回 ground_truth)

    const comparisonData = computed(() => {
      const map: Record<string, any> = {}

      // 遍历任务, 以 patient_id-combination_id 为 key 避免跨日期覆盖
      for (const task of tasks.value) {
        const key = `${task.patient_id}-${task.combination_id}`
        // 优先使用后端返回的 ground_task (按 patient_id 精确关联)
        const gt = task.ground_truth || null
        const llm = task.structured_result || {}
        map[key] = {
          id: task.id,
          task,
          patient_id: task.patient_id,
          record_id: task.record_id,
          date: task.date || '',
          status: task.status,
          error_type: task.error_type,
          error_message: task.error_message,
          total_duration: task.total_duration,
          full_transcript: task.full_transcript,
          hasTask: true,
          // 真实值 (来自 ground_truth)
          gt_right: gt ? gt.right_follicle_total : undefined,
          gt_left: gt ? gt.left_follicle_total : undefined,
          gt_endo_thick: gt ? gt.endometrium_thickness : undefined,
          gt_endo_type: gt ? gt.endometrium_type : undefined,
          gt_r_ovary: gt ? formatOvary(gt.right_ovary_length, gt.right_ovary_width) : '-',
          gt_l_ovary: gt ? formatOvary(gt.left_ovary_length, gt.left_ovary_width) : '-',
          gt_remark: gt ? gt.remark : undefined,
          // LLM 识别值
          llm_right: llm.right_follicle_total,
          llm_left: llm.left_follicle_total,
          llm_endo_thick: llm.endometrium_thickness,
          llm_endo_type: llm.endometrium_type,
          llm_r_ovary: formatOvary(llm.right_ovary_length, llm.right_ovary_width),
          llm_l_ovary: formatOvary(llm.left_ovary_length, llm.left_ovary_width),
          llm_remark: llm.remark,
        }
      }

      // 添加 selected_patient_ids 中但还没有任务的患者 (如实验新建但未启动)
      // 由于没有 task 信息, 此时显示为 pending, 日期留空
      if (batch.value?.selected_patient_ids) {
        for (const recordId of batch.value.selected_patient_ids) {
          const key = `pending-${recordId}`
          if (!map[key]) {
            map[key] = {
              id: null,
              task: null,
              patient_id: null,
              record_id: recordId,
              date: '',
              status: 'pending',
              error_type: undefined,
              error_message: undefined,
              total_duration: null,
              full_transcript: '',
              hasTask: false,
              gt_right: undefined,
              gt_left: undefined,
              gt_endo_thick: undefined,
              gt_endo_type: undefined,
              gt_r_ovary: '-',
              gt_l_ovary: '-',
              gt_remark: undefined,
              llm_right: undefined,
              llm_left: undefined,
              llm_endo_thick: undefined,
              llm_endo_type: undefined,
              llm_r_ovary: '-',
              llm_l_ovary: '-',
              llm_remark: undefined,
            }
          }
        }
      }

      return Object.values(map).sort((a: any, b: any) => {
        // 先按日期, 再按病历号排序
        if (a.date !== b.date) return a.date.localeCompare(b.date)
        return a.record_id.localeCompare(b.record_id)
      })
    })

    function formatOvary(l: number | undefined, w: number | undefined): string {
      return l && w ? `${l}×${w}` : '-'
    }

    const filteredTasks = computed(() => {
      if (!batch.value) return []
      let data = comparisonData.value
      if (filter.value === 'with_result') {
        data = data.filter((d) => d.llm_right !== undefined)
      } else if (filter.value === 'mismatch') {
        data = data.filter((d) => {
          return (
            d.gt_right !== d.llm_right ||
            d.gt_left !== d.llm_left ||
            d.gt_endo_thick !== d.llm_endo_thick ||
            d.gt_endo_type !== d.llm_endo_type ||
            d.gt_remark !== d.llm_remark
          )
        })
      }
      return data
    })

    async function handleStart() {
      try {
        await experimentApi.start(batchId.value)
        message.success('实验已启动')
        fetchData()
      } catch {
        message.error('启动失败')
      }
    }

    async function handlePause() {
      try {
        await experimentApi.pause(batchId.value)
        message.success('实验已暂停')
        fetchData()
      } catch {
        message.error('暂停失败')
      }
    }

    async function handleResume() {
      try {
        await experimentApi.resume(batchId.value)
        message.success('实验已继续')
        fetchData()
      } catch {
        message.error('继续失败')
      }
    }

    async function handleRetryFailed() {
      try {
        await experimentApi.retry(batchId.value)
        message.success('已重试失败任务')
        fetchData()
      } catch {
        message.error('重试失败')
      }
    }

    onMounted(() => {
      fetchData()
      fetchTasks()
      loadModels()
    })

    return {
      batchId, batch, tasks, filter, progress, filteredTasks,
      fetchData, handleStart, handlePause, handleResume, handleRetryFailed,
      ArrowLeftOutlined, ReloadOutlined,
      get_model_name,
      fieldModal, openFieldModal, closeFieldModal,
      comboModalOpen, comboCreating, asrModels, llmModels, promptTemplates,
      comboForm, hotwordsRaw, showComboModal, handleAddCombo, onPromptTemplateChange,
    }
  },
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
