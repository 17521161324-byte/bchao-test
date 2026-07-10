<template>
  <div class="page-container">
    <div class="page-header">
      <h2>实验详情 - {{ batch?.name || '' }}</h2>
      <a-space>
        <router-link to="/experiments"><a-button><ArrowLeftOutlined />返回列表</a-button></router-link>
        <a-button @click="refreshAll"><ReloadOutlined />刷新</a-button>
      </a-space>
    </div>

    <a-card size="small" style="margin-bottom: 16px" v-if="batch">
      <a-row :gutter="16">
        <a-col :span="3">状态: <a-tag :color="statusColor">{{ batch.status }}</a-tag></a-col>
        <a-col :span="3">患者数: {{ batch.patient_count || selectedPatientIds.length }}人</a-col>
        <a-col :span="3">组合数: {{ (batch.combinations || []).length }}</a-col>
        <a-col :span="3">总任务: {{ batch.total_tasks }}</a-col>
        <a-col :span="3">成功: <span style="color:#52c41a">{{ progress?.success || 0 }}</span></a-col>
        <a-col :span="3">失败: <span style="color:#ff4d4f">{{ progress?.failed || 0 }}</span></a-col>
        <a-col :span="3">进行中: <span style="color:#1890ff">{{ progress?.running || 0 }}</span></a-col>
      </a-row>
    </a-card>

    <a-space style="margin-bottom: 16px">
      <a-button type="primary" @click="handleStart" :disabled="batch?.status === 'running' || !batch?.combinations?.length">开始实验</a-button>
      <a-button @click="handlePause" v-if="batch?.status === 'running'">暂停</a-button>
      <a-button @click="handleResume" v-if="batch?.status === 'paused'">继续</a-button>
      <a-button @click="handleRetryFailed" v-if="(batch?.failure_count || 0) > 0">重试失败</a-button>
    </a-space>

    <a-card size="small" style="margin-bottom: 16px">
      <template #title>
        <a-space>
          <span>实验组合 ({{ (batch.combinations || []).length }})</span>
          <a-button size="small" type="primary" @click="showComboModal = true">+ 添加组合</a-button>
        </a-space>
      </template>
      <a-table v-if="batch?.combinations?.length" :data-source="batch.combinations" size="small" row-key="id" :pagination="false">
        <a-table-column title="ID" data-index="id" :width="60" />
        <a-table-column title="ASR模型" data-index="asr_model_name" />
        <a-table-column title="LLM模型" data-index="llm_model_name" />
        <a-table-column title="提示词模板" data-index="prompt_name" />
        <a-table-column title="热词" :width="120">
          <template #default="{ record }">{{ (record.hotwords || []).slice(0, 3).join(', ') }}{{ (record.hotwords || []).length > 3 ? '...' : '' }}</template>
        </a-table-column>
        <a-table-column title="状态" :width="80">
          <template #default="{ record }"><a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag></template>
        </a-table-column>
      </a-table>
      <a-empty v-else description="暂无组合,请点击上方按钮添加" style="padding: 12px 0" />
    </a-card>

    <a-tabs v-model:activeKey="activeTab" type="card">
      <a-tab-pane key="overview" tab="概览">
        <a-row :gutter="16" style="margin-bottom: 16px">
          <a-col :span="4"><a-statistic title="总任务" :value="localMetrics.total_tasks || 0" /></a-col>
          <a-col :span="4"><a-statistic title="成功" :value="localMetrics.success_count || 0" :value-style="{ color: '#52c41a' }" /></a-col>
          <a-col :span="4"><a-statistic title="失败" :value="localMetrics.failure_count || 0" :value-style="{ color: '#ff4d4f' }" /></a-col>
          <a-col :span="4"><a-statistic title="患者数" :value="localMetrics.patient_count || 0" /></a-col>
          <a-col :span="4"><a-statistic title="ASR复用" :value="asrStats.reused" /></a-col>
          <a-col :span="4"><a-statistic title="ASR新生成" :value="asrStats.generated" /></a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="4"><a-statistic title="内膜厚度" :value="(localMetrics.field_accuracy?.endometrium_thickness * 100).toFixed(0)" suffix="%" /></a-col>
          <a-col :span="4"><a-statistic title="内膜类型" :value="(localMetrics.field_accuracy?.endometrium_type * 100).toFixed(0)" suffix="%" /></a-col>
          <a-col :span="4"><a-statistic title="卵巢" :value="(localMetrics.field_accuracy?.ovary_size * 100).toFixed(0)" suffix="%" /></a-col>
          <a-col :span="4"><a-statistic title="卵泡" :value="(localMetrics.field_accuracy?.follicle * 100).toFixed(0)" suffix="%" /></a-col>
        </a-row>
      </a-tab-pane>

      <a-tab-pane key="tasks" :tab="`任务明细 (${tasks.length})`">
        <a-table :data-source="tasks" :loading="loading" size="small" row-key="id" :scroll="{ x: 1200 }"
          :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }">
          <a-table-column title="病历号" data-index="record_id" :width="100" />
          <a-table-column title="日期" data-index="date" :width="100" />
          <a-table-column title="组合ID" data-index="combination_id" :width="80" />
          <a-table-column title="ASR模型" :width="120"><template #default="{ record }">{{ record.asr_model_name || record.combination_asr_name || '-' }}</template></a-table-column>
          <a-table-column title="ASR来源" :width="90"><template #default="{ record }"><a-tag v-if="record.asr_source === 'reused'" color="blue">复用</a-tag><a-tag v-else-if="record.asr_source === 'generated'" color="green">新生成</a-tag><a-tag v-else-if="record.asr_source === 'failed'" color="red">失败</a-tag><a-tag v-else color="default">-</a-tag></template></a-table-column>
          <a-table-column title="LLM模型" :width="120"><template #default="{ record }">{{ record.llm_model_name || record.combination_llm_name || '-' }}</template></a-table-column>
          <a-table-column title="提示词模板" :width="140"><template #default="{ record }">{{ record.prompt_template_name || record.combination_prompt_name || '-' }}</template></a-table-column>
          <a-table-column title="状态" :width="80"><template #default="{ record }"><a-tag :color="record.status === 'success' ? 'green' : record.status === 'failed' ? 'red' : record.status === 'running' ? 'blue' : 'default'">{{ record.status }}</a-tag></template></a-table-column>
          <a-table-column title="准确率" :width="80"><template #default="{ record }">{{ record.accuracy != null ? (record.accuracy * 100).toFixed(0) + '%' : '-' }}</template></a-table-column>
          <a-table-column title="操作" :width="80" fixed="right"><template #default="{ record }"><a-button size="small" type="link" @click="openTaskDetail(record)">查看</a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="combinations" tab="组合对比">
        <a-table :data-source="combinationMetrics" size="small" row-key="combination_id" :scroll="{ x: 1400 }" :pagination="{ pageSize: 20 }">
          <a-table-column title="组合ID" data-index="combination_id" :width="80" />
          <a-table-column title="ASR模型" data-index="asr_model_name" :width="120" />
          <a-table-column title="LLM模型" data-index="llm_model_name" :width="120" />
          <a-table-column title="提示词模板" data-index="prompt_template_name" :width="140" />
          <a-table-column title="总任务" data-index="total" :width="70" />
          <a-table-column title="成功" data-index="success" :width="60" />
          <a-table-column title="失败" data-index="failure" :width="60" />
          <a-table-column title="成功率" :width="80"><template #default="{ record }">{{ (record.success_rate * 100).toFixed(0) }}%</template></a-table-column>
          <a-table-column title="平均准确率" :width="90"><template #default="{ record }">{{ (record.avg_accuracy * 100).toFixed(0) }}%</template></a-table-column>
          <a-table-column title="ASR复用率" :width="90"><template #default="{ record }">{{ (record.asr_reuse_rate * 100).toFixed(0) }}%</template></a-table-column>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="patients" tab="患者对比">
        <a-table :data-source="patientComparison" size="small" :scroll="{ x: 1800 }" row-key="key"
          :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }">
          <a-table-column title="病历号" data-index="record_id" :width="100" fixed="left" />
          <a-table-column title="日期" data-index="date" :width="100" />
          <a-table-column title="ASR模型" :width="120"><template #default="{ record }">{{ record.asr_model_name || '-' }}</template></a-table-column>
          <a-table-column title="LLM模型" :width="120"><template #default="{ record }">{{ record.llm_model_name || '-' }}</template></a-table-column>
          <a-table-column title="右卵泡" :width="120"><template #default="{ record }"><div>金标: {{ record.gt_right ?? '-' }}</div><div :style="{ color: record.gt_right !== record.llm_right ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_right ?? '-' }}</div></template></a-table-column>
          <a-table-column title="左卵泡" :width="120"><template #default="{ record }"><div>金标: {{ record.gt_left ?? '-' }}</div><div :style="{ color: record.gt_left !== record.llm_left ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_left ?? '-' }}</div></template></a-table-column>
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <a-modal v-model:open="showComboModal" title="添加实验组合" width="700px" :confirm-loading="comboCreating" @ok="handleAddCombo">
      <a-form layout="vertical" size="small">
        <a-form-item label="ASR 模型" required><a-select v-model:value="comboForm.asr_model_id" placeholder="选择 ASR 模型" show-search><a-select-option v-for="m in asrModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option></a-select></a-form-item>
        <a-form-item label="LLM 模型"><a-select v-model:value="comboForm.llm_model_id" placeholder="不使用 LLM" allow-clear show-search><a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option></a-select></a-form-item>
        <a-form-item label="提示词模板"><a-input v-model:value="comboForm.prompt_name" placeholder="输入模板名称" /></a-form-item>
        <a-form-item label="提示词内容"><a-textarea v-model:value="comboForm.prompt_template" :rows="8" placeholder="提示词内容..." /></a-form-item>
        <a-form-item label="热词 (每行一个)"><a-textarea v-model:value="hotwordsRaw" :rows="3" placeholder="卵泡&#10;内膜&#10;卵巢" /></a-form-item>
        <a-alert type="info" message="批量实验会优先复用数据管理中同一检查记录 + 同一ASR模型的成功转写结果;没有成功结果时才会调用ASR。" show-icon />
      </a-form>
    </a-modal>

    <a-modal v-model:open="taskDetailVisible" :title="`任务详情 - ${selectedTask?.record_id || ''}`" width="900px" :footer="null">
      <template v-if="selectedTask">
        <a-descriptions :column="2" bordered size="small" style="margin-bottom: 12px">
          <a-descriptions-item label="病历号">{{ selectedTask.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ selectedTask.date }}</a-descriptions-item>
          <a-descriptions-item label="组合ID">{{ selectedTask.combination_id }}</a-descriptions-item>
          <a-descriptions-item label="ASR模型">{{ selectedTask.asr_model_name || selectedTask.combination_asr_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="ASR来源"><a-tag v-if="selectedTask.asr_source === 'reused'" color="blue">复用</a-tag><a-tag v-else-if="selectedTask.asr_source === 'generated'" color="green">新生成</a-tag><a-tag v-else-if="selectedTask.asr_source === 'failed'" color="red">失败</a-tag><a-tag v-else color="default">-</a-tag></a-descriptions-item>
          <a-descriptions-item label="LLM模型">{{ selectedTask.llm_model_name || selectedTask.combination_llm_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="提示词模板">{{ selectedTask.prompt_template_name || selectedTask.combination_prompt_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="状态"><a-tag :color="selectedTask.status === 'success' ? 'green' : selectedTask.status === 'failed' ? 'red' : 'blue'">{{ selectedTask.status }}</a-tag></a-descriptions-item>
          <a-descriptions-item label="准确率">{{ selectedTask.accuracy != null ? (selectedTask.accuracy * 100).toFixed(0) + '%' : '-' }}</a-descriptions-item>
          <a-descriptions-item label="错误信息" :span="2">{{ selectedTask.error_message || '-' }}</a-descriptions-item>
        </a-descriptions>
        <a-tabs v-model:activeKey="taskDetailTab" size="small">
          <a-tab-pane key="asr" tab="ASR转写"><div class="text-box">{{ selectedTask.full_transcript || '(无)' }}</div></a-tab-pane>
          <a-tab-pane key="llm" tab="LLM输出"><pre class="code-box">{{ selectedTask.llm_raw_output || '(无)' }}</pre></a-tab-pane>
          <a-tab-pane key="structured" tab="结构化结果"><pre class="code-box">{{ JSON.stringify(selectedTask.structured_result, null, 2) || '(无)' }}</pre></a-tab-pane>
          <a-tab-pane key="ground" tab="真实B超"><pre class="code-box">{{ JSON.stringify(selectedTask.ground_truth, null, 2) || '(无)' }}</pre></a-tab-pane>
          <a-tab-pane key="eval" tab="评估对比"><pre class="code-box">{{ JSON.stringify(selectedTask.evaluation, null, 2) || '(无)' }}</pre></a-tab-pane>
        </a-tabs>
      </template>
    </a-modal>
  </div>
</template>
<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { experimentApi } from '@/api/experiment'
import { modelApi, promptTemplateApi } from '@/api/client'

export default defineComponent({
  name: 'ExperimentDetail',
  setup() {
    const route = useRoute()
    const batchId = computed(() => Number(route.params.id))
    const batch = ref<any>(null)
    const tasks = ref<any[]>([])
    const loading = ref(false)
    const progress = ref<any>(null)
    const activeTab = ref('overview')

    const taskDetailVisible = ref(false)
    const selectedTask = ref<any>(null)
    const taskDetailTab = ref('asr')

    const showComboModal = ref(false)
    const comboCreating = ref(false)
    const hotwordsRaw = ref('')
    const promptTemplates = ref<any[]>([])
    const asrModels = ref<any[]>([])
    const llmModels = ref<any[]>([])
    const comboForm = reactive<any>({ asr_model_id: null, llm_model_id: null, prompt_template_id: undefined, prompt_template: '' })

    const selectedPatientIds = computed(() => batch.value?.selected_patient_ids || [])
    const statusColor = computed(() => {
      const s = batch.value?.status
      return s === 'completed' ? 'green' : s === 'running' ? 'blue' : s === 'failed' ? 'red' : 'default'
    })

    const localMetrics = computed(() => {
      const total = tasks.value.length
      const successTasks = tasks.value.filter((t) => t.status === 'success')
      const failureTasks = tasks.value.filter((t) => t.status === 'failed')
      const evalTasks = successTasks.filter((t) => t.evaluation)
      const patientIds = new Set(tasks.value.map((t) => t.patient_id))
      const fieldMatchRate = (field: string) => !evalTasks.length ? 0 : evalTasks.filter((t) => t.evaluation?.fields?.[field]?.match).length / evalTasks.length
      return {
        total_tasks: total, success_count: successTasks.length, failure_count: failureTasks.length, patient_count: patientIds.size,
        field_accuracy: {
          endometrium_thickness: fieldMatchRate('endometrium_thickness'),
          endometrium_type: fieldMatchRate('endometrium_type'),
          ovary_size: fieldMatchRate('ovary_length') ,
          follicle: fieldMatchRate('follicle_total'),
          remark: fieldMatchRate('remark'),
        },
      }
    })

    const asrStats = computed(() => {
      const reused = tasks.value.filter((t) => t.asr_source === 'reused').length
      const generated = tasks.value.filter((t) => t.asr_source === 'generated').length
      const failed = tasks.value.filter((t) => t.asr_source === 'failed').length
      const total = tasks.value.length
      return { reused, generated, failed, total, reuse_rate: total > 0 ? reused / total : 0 }
    })

    const combinationMetrics = computed(() => {
      const map: Record<number, any> = {}
      for (const t of tasks.value) {
        const cid = t.combination_id
        if (!map[cid]) map[cid] = { combination_id: cid, asr_model_name: t.asr_model_name || t.combination_asr_name || '-', llm_model_name: t.llm_model_name || t.combination_llm_name || '-', prompt_template_name: t.prompt_template_name || t.combination_prompt_name || '-', total: 0, success: 0, failure: 0, accuracy_sum: 0, accuracy_count: 0, asr_reuse: 0, asr_generated: 0, asr_failed: 0 }
        const m = map[cid]
        m.total++
        if (t.status === 'success') { m.success++; m.accuracy_sum += (t.accuracy || 0); m.accuracy_count++ }
        else if (t.status === 'failed') m.failure++
        if (t.asr_source === 'reused') m.asr_reuse++
        else if (t.asr_source === 'generated') m.asr_generated++
        else if (t.asr_source === 'failed') m.asr_failed++
      }
      return Object.values(map).map((m: any) => ({ ...m, success_rate: m.total > 0 ? m.success / m.total : 0, avg_accuracy: m.accuracy_count > 0 ? m.accuracy_sum / m.accuracy_count : 0, asr_reuse_rate: m.total > 0 ? m.asr_reuse / m.total : 0 }))
    })

    const patientComparison = computed(() => tasks.value.map((t) => ({
      key: t.patient_id + '-' + t.combination_id,
      record_id: t.record_id, date: t.date || '',
      asr_model_name: t.asr_model_name || t.combination_asr_name || '-',
      llm_model_name: t.llm_model_name || t.combination_llm_name || '-',
      gt_right: t.ground_truth?.right_follicle_total,
      gt_left: t.ground_truth?.left_follicle_total,
      gt_endo_thick: t.ground_truth?.endometrium_thickness,
      gt_endo_type: t.ground_truth?.endometrium_type,
      gt_r_ovary: t.ground_truth?.right_ovary_length && t.ground_truth?.right_ovary_width ? t.ground_truth.right_ovary_length + '*' + t.ground_truth.right_ovary_width : '-',
      gt_l_ovary: t.ground_truth?.left_ovary_length && t.ground_truth?.left_ovary_width ? t.ground_truth.left_ovary_length + '*' + t.ground_truth.left_ovary_width : '-',
      llm_right: t.structured_result?.right_follicle_total,
      llm_left: t.structured_result?.left_follicle_total,
      llm_endo_thick: t.structured_result?.endometrium_thickness,
      llm_endo_type: t.structured_result?.endometrium_type,
      llm_r_ovary: t.structured_result?.right_ovary_length && t.structured_result?.right_ovary_width ? t.structured_result.right_ovary_length + '*' + t.structured_result.right_ovary_width : '-',
      llm_l_ovary: t.structured_result?.left_ovary_length && t.structured_result?.left_ovary_width ? t.structured_result.left_ovary_length + '*' + t.structured_result.left_ovary_width : '-',
    })))

    async function fetchData() {
      try {
        const res = await experimentApi.get(batchId.value)
        batch.value = res?.data || res || null
      } catch { message.error('加载失败') }
    }
    async function fetchProgress() { try { progress.value = await experimentApi.progress(batchId.value) } catch {} }
    async function fetchTasks() { try { const res = await experimentApi.tasks(batchId.value); tasks.value = Array.isArray(res) ? res : (res.data || []) } catch {} }
    async function refreshAll() { loading.value = true; try { await fetchData(); await fetchTasks(); } finally { loading.value = false } }
    function openTaskDetail(task: any) { selectedTask.value = task; taskDetailVisible.value = true; taskDetailTab.value = 'asr' }
    async function handleStart() { try { await experimentApi.start(batchId.value); message.success('实验已启动'); refreshAll() } catch { message.error('启动失败') } }
    async function handlePause() { try { await experimentApi.pause(batchId.value); message.success('已暂停'); refreshAll() } catch { message.error('暂停失败') } }
    async function handleResume() { try { await experimentApi.resume(batchId.value); message.success('已继续'); refreshAll() } catch { message.error('继续失败') } }
    async function handleRetryFailed() { try { await experimentApi.retry(batchId.value); message.success('已重试失败任务'); refreshAll() } catch { message.error('重试失败') } }
    function onPromptTemplateChange(id: number) { const tmpl = promptTemplates.value.find((t: any) => t.id === id); if (tmpl) comboForm.prompt_template = tmpl.content }
    async function handleAddCombo() {
      if (!comboForm.asr_model_id) { message.error('请选择 ASR 模型'); return }
      comboCreating.value = true
      try {
        await experimentApi.addCombination(batchId.value, {
          asr_model_id: comboForm.asr_model_id,
          llm_model_id: comboForm.llm_model_id || null,
          prompt_name: comboForm.prompt_name || '',
          prompt_template: comboForm.prompt_template || '',
          hotwords: hotwordsRaw.value.split('\n').map((s: string) => s.trim()).filter(Boolean),
        })
        message.success('组合添加成功'); showComboModal.value = false; refreshAll()
      } catch { message.error('添加失败') }
      finally { comboCreating.value = false }
    }
    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        asrModels.value = asr || []; llmModels.value = llm || []
      } catch {}
    }
    async function loadPromptTemplates() { try { promptTemplates.value = (await promptTemplateApi.list()) || [] } catch {} }

    onMounted(() => { refreshAll(); loadModels(); loadPromptTemplates() })

    return { batchId, batch, tasks, loading, progress, activeTab, selectedPatientIds, statusColor, localMetrics, asrStats, combinationMetrics, patientComparison, taskDetailVisible, selectedTask, taskDetailTab, showComboModal, comboCreating, hotwordsRaw, comboForm: { ...comboForm }, asrModels, llmModels, promptTemplates, refreshAll, handleStart, handlePause, handleResume, handleRetryFailed, openTaskDetail, handleAddCombo, onPromptTemplateChange, ArrowLeftOutlined, ReloadOutlined }
  },
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.text-box { background: #f5f5f5; padding: 12px; border-radius: 6px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-size: 13px; line-height: 1.7; }
.code-box { background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; }
</style>
