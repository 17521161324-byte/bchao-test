<template>
  <div class="page-container">
    <!-- 顶部信息 + 控制按钮 -->
    <div class="page-header">
      <h2>实验详情 - {{ batch?.name || '' }}</h2>
      <a-space>
        <router-link to="/experiments"><a-button><ArrowLeftOutlined />返回列表</a-button></router-link>
        <a-button @click="refreshAll"><ReloadOutlined />刷新</a-button>
      </a-space>
    </div>

    <!-- 概览卡片 -->
    <a-card size="small" style="margin-bottom: 16px" v-if="batch">
      <a-row :gutter="16">
        <a-col :span="3">状态: <a-tag :color="statusColor">{{ batch.status }}</a-tag></a-col>
        <a-col :span="3">患者数: {{ batch.patient_count || (selectedPatientIds.length) }}人</a-col>
        <a-col :span="3">组合数: {{ (batch.combinations || []).length }}</a-col>
        <a-col :span="3">总任务: {{ batch.total_tasks }}</a-col>
        <a-col :span="3">成功: <span style="color:#52c41a">{{ progress?.success || 0 }}</span></a-col>
        <a-col :span="3">失败: <span style="color:#ff4d4f">{{ progress?.failed || 0 }}</span></a-col>
        <a-col :span="3">进行中: <span style="color:#1890ff">{{ progress?.running || 0 }}</span></a-col>
      </a-row>
    </a-card>

    <!-- 控制按钮 -->
    <a-space style="margin-bottom: 16px">
      <a-button type="primary" @click="handleStart" :disabled="batch?.status === 'running' || !batch?.combinations?.length">开始实验</a-button>
      <a-button @click="handlePause" v-if="batch?.status === 'running'">暂停</a-button>
      <a-button @click="handleResume" v-if="batch?.status === 'paused'">继续</a-button>
      <a-button @click="handleRetryFailed" v-if="(batch?.failure_count || 0) > 0">重试失败</a-button>
    </a-space>

    <!-- 主 Tab -->
    <a-tabs v-model:activeKey="activeTab" type="card">
      <!-- 概览 Tab -->
      <a-tab-pane key="overview" tab="概览">
        <a-row :gutter="16" style="margin-bottom: 16px">
          <a-col :span="6"><a-statistic title="总任务" :value="metrics?.total_tasks || 0" /></a-col>
          <a-col :span="6"><a-statistic title="成功" :value="metrics?.success_count || 0" :value-style="{ color: '#52c41a' }" /></a-col>
          <a-col :span="6"><a-statistic title="失败" :value="metrics?.failure_count || 0" :value-style="{ color: '#ff4d4f' }" /></a-col>
          <a-col :span="6"><a-statistic title="平均准确率" :value="((metrics?.field_accuracy?.endometrium_thickness || 0) * 100).toFixed(0)" suffix="%" /></a-col>
        </a-row>
        <a-row :gutter="16" style="margin-bottom: 16px">
          <a-col :span="6"><a-statistic title="ASR复用数" :value="batch?.asr_reuse_count || 0" /></a-col>
          <a-col :span="6"><a-statistic title="ASR新生成数" :value="batch?.asr_generated_count || 0" /></a-col>
          <a-col :span="6"><a-statistic title="ASR失败数" :value="batch?.asr_failed_count || 0" /></a-col>
          <a-col :span="6"><a-statistic title="ASR复用率" :value="((batch?.asr_reuse_rate || 0) * 100).toFixed(0)" suffix="%" /></a-col>
        </a-row>
        <a-card title="字段准确率" size="small">
          <a-descriptions :column="3" bordered size="small" v-if="metrics">
            <a-descriptions-item label="内膜厚度">{{ ((metrics.field_accuracy?.endometrium_thickness || 0) * 100).toFixed(0) }}%</a-descriptions-item>
            <a-descriptions-item label="内膜类型">{{ ((metrics.field_accuracy?.endometrium_type || 0) * 100).toFixed(0) }}%</a-descriptions-item>
            <a-descriptions-item label="卵巢">{{ ((metrics.field_accuracy?.ovary_size || 0) * 100).toFixed(0) }}%</a-descriptions-item>
            <a-descriptions-item label="卵泡">{{ ((metrics.field_accuracy?.follicle || 0) * 100).toFixed(0) }}%</a-descriptions-item>
            <a-descriptions-item label="备注">{{ ((metrics.field_accuracy?.remark || 0) * 100).toFixed(0) }}%</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-tab-pane>

      <!-- 任务明细 Tab -->
      <a-tab-pane key="tasks" :tab="`任务明细 (${tasks.length})`">
        <a-table
          :data-source="tasks"
          :loading="loading"
          size="small"
          row-key="id"
          :scroll="{ x: 1200 }"
          :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        >
          <a-table-column title="病历号" data-index="record_id" :width="100" />
          <a-table-column title="日期" data-index="date" :width="100" />
          <a-table-column title="ASR模型" :width="120">
            <template #default="{ record }">{{ record.asr_model_name || record.combination_asr_name || '-' }}</template>
          </a-table-column>
          <a-table-column title="ASR来源" :width="90">
            <template #default="{ record }">
              <a-tag v-if="record.asr_source === 'reused'" color="blue">复用</a-tag>
              <a-tag v-else-if="record.asr_source === 'generated'" color="green">新生成</a-tag>
              <a-tag v-else-if="record.asr_source === 'failed'" color="red">失败</a-tag>
              <a-tag v-else color="default">-</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="LLM模型" :width="120">
            <template #default="{ record }">{{ record.llm_model_name || record.combination_llm_name || '-' }}</template>
          </a-table-column>
          <a-table-column title="提示词模板" :width="140">
            <template #default="{ record }">{{ record.prompt_template_name || record.combination_prompt_name || '-' }}</template>
          </a-table-column>
          <a-table-column title="状态" :width="80">
            <template #default="{ record }">
              <a-tag :color="record.status === 'success' ? 'green' : record.status === 'failed' ? 'red' : record.status === 'running' ? 'blue' : 'default'">
                {{ record.status }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="准确率" :width="80">
            <template #default="{ record }">{{ record.accuracy != null ? (record.accuracy * 100).toFixed(0) + '%' : '-' }}</template>
          </a-table-column>
          <a-table-column title="错误" :width="120">
            <template #default="{ record }">
              <a-tooltip v-if="record.error_message" :title="record.error_message">
                <span style="color: #ff4d4f">{{ record.error_type || '错误' }}</span>
              </a-tooltip>
              <span v-else>-</span>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="80" fixed="right">
            <template #default="{ record }"><a-button size="small" type="link" @click="openTaskDetail(record)">查看</a-button></template>
          </a-table-column>
        </a-table>
      </a-tab-pane>

      <!-- 组合对比 Tab -->
      <a-tab-pane key="combinations" tab="组合对比">
        <a-table
          :data-source="combinationMetrics"
          size="small"
          row-key="combination_id"
          :scroll="{ x: 1400 }"
          :pagination="{ pageSize: 20 }"
        >
          <a-table-column title="组合ID" data-index="combination_id" :width="80" />
          <a-table-column title="ASR模型" data-index="asr_model_name" :width="120" />
          <a-table-column title="LLM模型" data-index="llm_model_name" :width="120" />
          <a-table-column title="提示词模板" data-index="prompt_template_name" :width="140" />
          <a-table-column title="总任务" data-index="total" :width="70" />
          <a-table-column title="成功" data-index="success" :width="60" />
          <a-table-column title="失败" data-index="failure" :width="60" />
          <a-table-column title="成功率" :width="80">
            <template #default="{ record }">{{ (record.success_rate * 100).toFixed(0) }}%</template>
          </a-table-column>
          <a-table-column title="平均准确率" :width="90">
            <template #default="{ record }">{{ (record.avg_accuracy * 100).toFixed(0) }}%</template>
          </a-table-column>
          <a-table-column title="ASR复用率" :width="90">
            <template #default="{ record }">{{ (record.asr_reuse_rate * 100).toFixed(0) }}%</template>
          </a-table-column>
        </a-table>
      </a-tab-pane>

      <!-- 患者对比 Tab -->
      <a-tab-pane key="patients" tab="患者对比">
        <a-table
          :data-source="patientComparison"
          size="small"
          :scroll="{ x: 1800 }"
          row-key="key"
          :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
        >
          <a-table-column title="病历号" data-index="record_id" :width="100" fixed="left" />
          <a-table-column title="日期" data-index="date" :width="100" />
          <a-table-column title="ASR模型" :width="120">
            <template #default="{ record }">{{ record.asr_model_name || '-' }}</template>
          </a-table-column>
          <a-table-column title="LLM模型" :width="120">
            <template #default="{ record }">{{ record.llm_model_name || '-' }}</template>
          </a-table-column>
          <a-table-column title="右卵泡" :width="120">
            <template #default="{ record }">
              <div>金标: {{ record.gt_right ?? '-' }}</div>
              <div :style="{ color: record.gt_right !== record.llm_right ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_right ?? '-' }}</div>
            </template>
          </a-table-column>
          <a-table-column title="左卵泡" :width="120">
            <template #default="{ record }">
              <div>金标: {{ record.gt_left ?? '-' }}</div>
              <div :style="{ color: record.gt_left !== record.llm_left ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_left ?? '-' }}</div>
            </template>
          </a-table-column>
          <a-table-column title="内膜厚度" :width="100">
            <template #default="{ record }">
              <div>金标: {{ record.gt_endo_thick ?? '-' }}</div>
              <div :style="{ color: record.gt_endo_thick !== record.llm_endo_thick ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_endo_thick ?? '-' }}</div>
            </template>
          </a-table-column>
          <a-table-column title="内膜类型" :width="80">
            <template #default="{ record }">
              <div>金标: {{ record.gt_endo_type ?? '-' }}</div>
              <div :style="{ color: record.gt_endo_type !== record.llm_endo_type ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_endo_type ?? '-' }}</div>
            </template>
          </a-table-column>
          <a-table-column title="右卵巢" :width="100">
            <template #default="{ record }">
              <div>金标: {{ record.gt_r_ovary }}</div>
              <div :style="{ color: record.gt_r_ovary !== record.llm_r_ovary ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_r_ovary }}</div>
            </template>
          </a-table-column>
          <a-table-column title="左卵巢" :width="100">
            <template #default="{ record }">
              <div>金标: {{ record.gt_l_ovary }}</div>
              <div :style="{ color: record.gt_l_ovary !== record.llm_l_ovary ? '#ff4d4f' : '#52c41a' }">LLM: {{ record.llm_l_ovary }}</div>
            </template>
          </a-table-column>
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <!-- 任务详情弹窗 -->
    <a-modal
      v-model:open="taskDetailVisible"
      :title="`任务详情 - ${selectedTask?.record_id || ''}`"
      width="900px"
      :footer="null"
    >
      <template v-if="selectedTask">
        <a-descriptions :column="2" bordered size="small" style="margin-bottom: 12px">
          <a-descriptions-item label="病历号">{{ selectedTask.record_id }}</a-descriptions-item>
          <a-descriptions-item label="日期">{{ selectedTask.date }}</a-descriptions-item>
          <a-descriptions-item label="ASR模型">{{ selectedTask.asr_model_name || selectedTask.combination_asr_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="ASR来源">
            <a-tag v-if="selectedTask.asr_source === 'reused'" color="blue">复用</a-tag>
            <a-tag v-else-if="selectedTask.asr_source === 'generated'" color="green">新生成</a-tag>
            <a-tag v-else-if="selectedTask.asr_source === 'failed'" color="red">失败</a-tag>
            <a-tag v-else color="default">-</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="LLM模型">{{ selectedTask.llm_model_name || selectedTask.combination_llm_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="提示词模板">{{ selectedTask.prompt_template_name || selectedTask.combination_prompt_name || '-' }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="selectedTask.status === 'success' ? 'green' : selectedTask.status === 'failed' ? 'red' : 'blue'">{{ selectedTask.status }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="准确率">{{ selectedTask.accuracy != null ? (selectedTask.accuracy * 100).toFixed(0) + '%' : '-' }}</a-descriptions-item>
          <a-descriptions-item label="错误类型">{{ selectedTask.error_type || '-' }}</a-descriptions-item>
          <a-descriptions-item label="错误信息" :span="2">{{ selectedTask.error_message || '-' }}</a-descriptions-item>
        </a-descriptions>

        <a-tabs v-model:activeKey="taskDetailTab" size="small">
          <a-tab-pane key="asr" tab="ASR转写">
            <div class="text-box">{{ selectedTask.full_transcript || '(无)' }}</div>
          </a-tab-pane>
          <a-tab-pane key="llm" tab="LLM输出">
            <pre class="code-box">{{ selectedTask.llm_raw_output || '(无)' }}</pre>
          </a-tab-pane>
          <a-tab-pane key="structured" tab="结构化结果">
            <pre class="code-box">{{ JSON.stringify(selectedTask.structured_result, null, 2) || '(无)' }}</pre>
          </a-tab-pane>
          <a-tab-pane key="ground" tab="真实B超">
            <pre class="code-box">{{ JSON.stringify(selectedTask.ground_truth, null, 2) || '(无)' }}</pre>
          </a-tab-pane>
          <a-tab-pane key="eval" tab="评估对比">
            <pre class="code-box">{{ JSON.stringify(selectedTask.evaluation, null, 2) || '(无)' }}</pre>
          </a-tab-pane>
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
import type { ExperimentBatch, ExperimentTaskSummary } from '@/types/experiment'

export default defineComponent({
  name: 'ExperimentDetail',
  setup() {
    const route = useRoute()
    const batchId = computed(() => Number(route.params.id))
    const batch = ref<ExperimentBatch | null>(null)
    const tasks = ref<ExperimentTaskSummary[]>([])
    const filter = ref('all')
    const loading = ref(false)
    const progress = ref<any>(null)
    const activeTab = ref('overview')

    // 任务详情弹窗
    const taskDetailVisible = ref(false)
    const selectedTask = ref<ExperimentTaskSummary | null>(null)
    const taskDetailTab = ref('asr')

    const selectedPatientIds = computed(() => batch.value?.selected_patient_ids || [])

    const metrics = computed(() => batch.value?.metrics || null)

    const statusColor = computed(() => {
      const s = batch.value?.status
      if (s === 'completed') return 'green'
      if (s === 'running') return 'blue'
      if (s === 'failed') return 'red'
      return 'default'
    })

    // 按组合聚合指标
    const combinationMetrics = computed(() => {
      const map: Record<number, any> = {}
      for (const t of tasks.value) {
        const cid = t.combination_id
        if (!map[cid]) {
          map[cid] = {
            combination_id: cid,
            asr_model_name: t.asr_model_name || t.combination_asr_name || '-',
            llm_model_name: t.llm_model_name || t.combination_llm_name || '-',
            prompt_template_name: t.prompt_template_name || t.combination_prompt_name || '-',
            total: 0, success: 0, failure: 0,
            accuracy_sum: 0, accuracy_count: 0,
            asr_reuse: 0, asr_generated: 0, asr_failed: 0,
          }
        }
        const m = map[cid]
        m.total++
        if (t.status === 'success') { m.success++; m.accuracy_sum += (t.accuracy || 0); m.accuracy_count++ }
        else if (t.status === 'failed') { m.failure++ }
        if (t.asr_source === 'reused') m.asr_reuse++
        else if (t.asr_source === 'generated') m.asr_generated++
        else if (t.asr_source === 'failed') m.asr_failed++
      }
      return Object.values(map).map((m: any) => ({
        ...m,
        success_rate: m.total > 0 ? m.success / m.total : 0,
        avg_accuracy: m.accuracy_count > 0 ? m.accuracy_sum / m.accuracy_count : 0,
        asr_reuse_rate: m.total > 0 ? m.asr_reuse / m.total : 0,
      }))
    })

    // 患者对比 (按 exam_record_id + combination_id 唯一)
    const patientComparison = computed(() => {
      return tasks.value.map((t) => ({
        key: `${t.patient_id}-${t.combination_id}`,
        record_id: t.record_id,
        date: t.date || '',
        asr_model_name: t.asr_model_name || t.combination_asr_name || '-',
        llm_model_name: t.llm_model_name || t.combination_llm_name || '-',
        gt_right: t.ground_truth?.right_follicle_total,
        gt_left: t.ground_truth?.left_follicle_total,
        gt_endo_thick: t.ground_truth?.endometrium_thickness,
        gt_endo_type: t.ground_truth?.endometrium_type,
        gt_r_ovary: t.ground_truth?.right_ovary_length && t.ground_truth?.right_ovary_width
          ? `${t.ground_truth.right_ovary_length}×${t.ground_truth.right_ovary_width}` : '-',
        gt_l_ovary: t.ground_truth?.left_ovary_length && t.ground_truth?.left_ovary_width
          ? `${t.ground_truth.left_ovary_length}×${t.ground_truth.left_ovary_width}` : '-',
        llm_right: t.structured_result?.right_follicle_total,
        llm_left: t.structured_result?.left_follicle_total,
        llm_endo_thick: t.structured_result?.endometrium_thickness,
        llm_endo_type: t.structured_result?.endometrium_type,
        llm_r_ovary: t.structured_result?.right_ovary_length && t.structured_result?.right_ovary_width
          ? `${t.structured_result.right_ovary_length}×${t.structured_result.right_ovary_width}` : '-',
        llm_l_ovary: t.structured_result?.left_ovary_length && t.structured_result?.left_ovary_width
          ? `${t.structured_result.left_ovary_length}×${t.structured_result.left_ovary_width}` : '-',
      }))
    })

    async function fetchData() {
      try {
        const res = await experimentApi.get(batchId.value)
        batch.value = res.data || res
        fetchProgress()
      } catch {
        message.error('加载失败')
      }
    }

    async function fetchProgress() {
      try {
        const res = await experimentApi.progress(batchId.value)
        progress.value = res
      } catch { /* ignore */ }
    }

    async function fetchTasks() {
      try {
        const res = await experimentApi.tasks(batchId.value)
        tasks.value = res
      } catch { /* ignore */ }
    }

    async function refreshAll() {
      loading.value = true
      try {
        await fetchData()
        await fetchTasks()
        message.success('刷新成功')
      } finally {
        loading.value = false
      }
    }

    function openTaskDetail(task: ExperimentTaskSummary) {
      selectedTask.value = task
      taskDetailVisible.value = true
      taskDetailTab.value = 'asr'
    }

    async function handleStart() {
      try {
        await experimentApi.start(batchId.value)
        message.success('实验已启动')
        refreshAll()
      } catch { message.error('启动失败') }
    }

    async function handlePause() {
      try { await experimentApi.pause(batchId.value); message.success('已暂停'); refreshAll() }
      catch { message.error('暂停失败') }
    }

    async function handleResume() {
      try { await experimentApi.resume(batchId.value); message.success('已继续'); refreshAll() }
      catch { message.error('继续失败') }
    }

    async function handleRetryFailed() {
      try { await experimentApi.retry(batchId.value); message.success('已重试失败任务'); refreshAll() }
      catch { message.error('重试失败') }
    }

    onMounted(() => { refreshAll() })

    return {
      batchId, batch, tasks, filter, loading, progress, activeTab,
      selectedPatientIds, metrics, statusColor,
      combinationMetrics, patientComparison,
      taskDetailVisible, selectedTask, taskDetailTab,
      refreshAll, fetchData, handleStart, handlePause, handleResume, handleRetryFailed, openTaskDetail,
      ArrowLeftOutlined, ReloadOutlined,
    }
  },
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.text-box { background: #f5f5f5; padding: 12px; border-radius: 6px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-size: 13px; line-height: 1.7; }
.code-box { background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; }
</style>
