<template>
  <div class="page-container">
    <!-- 顶部操作栏 -->
    <div class="page-header">
      <h2>实验详情 - {{ batch?.name || '' }}</h2>
      <a-space>
        <router-link to="/experiments"><a-button><ArrowLeftOutlined /> 返回列表</a-button></router-link>
        <a-button @click="refreshAll"><ReloadOutlined /> 刷新</a-button>
        <a-button @click="handleExport">导出 Excel</a-button>
        <a-button type="primary" @click="handleStart" :disabled="!canStart">开始实验</a-button>
        <a-button @click="handlePause" v-if="batch?.status === 'running'">暂停</a-button>
        <a-button @click="handleResume" v-if="batch?.status === 'paused'">继续</a-button>
        <a-button @click="handleRetryFailed" v-if="(batch?.failure_count || 0) > 0">重试失败</a-button>
      </a-space>
    </div>

    <!-- 实验配置卡片 -->
    <a-card size="small" style="margin-bottom: 16px" v-if="batch">
      <a-row :gutter="16">
        <a-col :span="3">状态: <a-tag :color="statusColor">{{ batch.status }}</a-tag></a-col>
        <a-col :span="4">ASR: {{ config.asr_model_name || '-' }}</a-col>
        <a-col :span="4">LLM: {{ config.llm_model_name || '-' }}</a-col>
        <a-col :span="4">提示词: {{ config.prompt_name || '-' }}</a-col>
        <a-col :span="3">提示词状态: {{ config.has_prompt ? '已配置' : '未配置' }}</a-col>
        <a-col :span="3">记录数: {{ recordResults.length }}</a-col>
        <a-col :span="3">
          成功/失败/总:
          <span style="color: #52c41a">{{ progress?.success || batch.success_count || 0 }}</span> /
          <span style="color: #ff4d4f">{{ progress?.failed || batch.failure_count || 0 }}</span> /
          {{ batch.total_tasks || 0 }}
        </a-col>
      </a-row>
      <a-row :gutter="16" style="margin-top: 8px">
        <a-col :span="12">检查日期: {{ (batch.selected_dates || []).join(', ') }}</a-col>
        <a-col :span="6">创建: {{ batch.created_at ? String(batch.created_at).slice(0, 19) : '-' }}</a-col>
        <a-col :span="6">
          <a-alert v-if="batch.combinations && batch.combinations.length > 1" type="warning" :message="`历史多组合: ${batch.combinations.length} 个，仅展示第一个`" show-icon />
        </a-col>
      </a-row>
    </a-card>

    <!-- 检查记录结果对比表 -->
    <a-card>
      <template #title>
        <span>检查结果对比（{{ recordResults.length }} 条记录，{{ successCount }} 成功 / {{ failCount }} 失败）</span>
      </template>
      <a-table
        :data-source="recordResults"
        size="small"
        row-key="key"
        :scroll="{ x: 'max-content' }"
        :pagination="{ pageSize: 50, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }"
      >
        <a-table-column title="病历号" data-index="record_id" />
        <a-table-column title="日期" data-index="date" />
        <a-table-column title="ASR" data-index="asr_text" :width="60" align="center" />
        <a-table-column title="LLM" data-index="llm_text" :width="60" align="center" />
        <a-table-column title="内膜厚度" :width="90" align="center">
          <template #default="scope">{{ symbolFor(scope?.record?.endometrium_thickness_match) }}</template>
        </a-table-column>
        <a-table-column title="内膜类型" :width="90" align="center">
          <template #default="scope">{{ symbolFor(scope?.record?.endometrium_type_match) }}</template>
        </a-table-column>
        <a-table-column title="右卵巢" :width="80" align="center">
          <template #default="scope">{{ symbolFor(scope?.record?.right_ovary_match) }}</template>
        </a-table-column>
        <a-table-column title="左卵巢" :width="80" align="center">
          <template #default="scope">{{ symbolFor(scope?.record?.left_ovary_match) }}</template>
        </a-table-column>
        <a-table-column title="右卵泡" :width="80" align="center">
          <template #default="scope">{{ symbolFor(scope?.record?.right_follicle_match) }}</template>
        </a-table-column>
        <a-table-column title="左卵泡" :width="80" align="center">
          <template #default="scope">{{ symbolFor(scope?.record?.left_follicle_match) }}</template>
        </a-table-column>
        <a-table-column title="综合" :width="70" align="center">
          <template #default="scope">
            <a-tag v-if="scope?.record?.overall === 'match'" color="green">✓</a-tag>
            <a-tag v-else-if="scope?.record?.overall === 'mismatch'" color="red">✗</a-tag>
            <a-tag v-else>-</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="操作" :width="80" fixed="right">
          <template #default="scope"><a-button size="small" type="link" @click="openDetail(scope?.record)">详情</a-button></template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 单条详情抽屉（复用通用组件） -->
    <ExamDetailDrawer :visible="detailVisible" :data="detailData" @close="detailVisible = false" />
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { experimentApi } from '@/api/experiment'
import ExamDetailDrawer from '@/components/ExamDetailDrawer/index.vue'

function symbolFor(result: string): string {
  if (result === 'match') return '✅'
  if (result === 'mismatch') return '❌'
  return '-'
}

function compareF(real: any, extracted: any): 'match' | 'mismatch' | 'empty' {
  if (real == null && extracted == null) return 'empty'
  if (real == null || extracted == null) return 'empty'
  const a = String(real).trim()
  const b = String(extracted).trim()
  if (a === '' && b === '') return 'empty'
  if (a === '' || b === '') return 'empty'
  return a === b ? 'match' : 'mismatch'
}

export default defineComponent({
  name: 'ExperimentDetail',
  components: { ExamDetailDrawer },
  setup() {
    const route = useRoute()
    const batchId = computed(() => Number(route.params.id))
    const batch = ref<any>(null)
    const tasks = ref<any[]>([])
    const loading = ref(false)
    const progress = ref<any>(null)
    let pollTimer: ReturnType<typeof setInterval> | null = null

    const config = reactive<any>({
      asr_model_name: '',
      llm_model_name: '',
      prompt_name: '',
      has_prompt: false,
    })

    const detailVisible = ref(false)
    const detailData = ref<any>(null)

    const selectedPatientIds = computed(() => batch.value?.selected_patient_ids || [])
    const canStart = computed(() => batch.value && batch.value.status !== 'running' && (batch.value.combinations || []).length > 0)
    const statusColor = computed(() => {
      const s = batch.value?.status
      return s === 'completed' ? 'green' : s === 'running' ? 'blue' : s === 'failed' ? 'red' : 'default'
    })

    const successCount = computed(() => tasks.value.filter((t) => t.status === 'success').length)
    const failCount = computed(() => tasks.value.filter((t) => t.status === 'failed').length)

    const recordResults = computed(() => {
      return tasks.value.map((t) => {
        const ev = parseEval(t.evaluation)
        const fields = ev?.fields || {}
        const sr = t.structured_result || {}
        const gt = t.ground_truth || {}

        const em_thick = compareF(gt.endometrium_thickness, fields.endometrium_thickness?.identified ?? sr.endometrium_thickness)
        const em_type = compareF(gt.endometrium_type, fields.endometrium_type?.identified ?? sr.endometrium_type)
        const r_foll = compareF(gt.right_follicle_total, fields.right_follicle_total?.identified ?? sr.right_follicle_total)
        const l_foll = compareF(gt.left_follicle_total, fields.left_follicle_total?.identified ?? sr.left_follicle_total)

        const r_len = compareF(gt.right_ovary_length, fields.right_ovary_length?.identified ?? sr.right_ovary_length)
        const r_wid = compareF(gt.right_ovary_width, fields.right_ovary_width?.identified ?? sr.right_ovary_width)
        const r_ovary = (r_len === 'match' && r_wid === 'match') ? 'match' : (gt.right_ovary_length == null && gt.right_ovary_width == null) ? 'empty' : 'mismatch'

        const l_len = compareF(gt.left_ovary_length, fields.left_ovary_length?.identified ?? sr.left_ovary_length)
        const l_wid = compareF(gt.left_ovary_width, fields.left_ovary_width?.identified ?? sr.left_ovary_width)
        const l_ovary = (l_len === 'match' && l_wid === 'match') ? 'match' : (gt.left_ovary_length == null && gt.left_ovary_width == null) ? 'empty' : 'mismatch'

        const all = [em_thick, em_type, r_foll, l_foll, r_ovary, l_ovary]
        const overall = all.some((r) => r === 'mismatch') ? 'mismatch' : all.every((r) => r === 'empty') ? 'empty' : 'match'

        const asr_text = (t.asr_source === 'reused' || t.asr_source === 'generated') ? '✅' : t.asr_source === 'failed' ? '❌' : '-'
        const hasValid = sr && typeof sr === 'object' && Object.keys(sr).length > 0
        const llm_text = (t.status === 'success' && hasValid) ? '✅' : (['empty_structured_result', 'invalid_structured_schema', 'llm_failed'].includes(t.error_type)) ? '❌' : '-'

        return {
          key: `${t.record_id}-${t.date}-${t.id}`,
          record_id: t.record_id,
          date: t.date || '',
          asr_text,
          llm_text,
          endometrium_thickness_match: em_thick,
          endometrium_type_match: em_type,
          right_follicle_match: r_foll,
          left_follicle_match: l_foll,
          right_ovary_match: r_ovary,
          left_ovary_match: l_ovary,
          overall,
          task: t,
        }
      })
    })

    function buildDetailData(task: any): any {
      const sr = task.structured_result || {}
      const target = ['right_follicle_total', 'left_follicle_total', 'endometrium_thickness', 'endometrium_type', 'right_ovary_length', 'right_ovary_width', 'left_ovary_length', 'left_ovary_width']
      const missingFields = target.filter((f) => !(f in sr))
      return {
        record_id: task.record_id,
        date: task.date || '',
        segs_count: task.patient?.segs?.length || 0,
        has_ground_truth: !!(task.ground_truth || task.patient?.result),
        asr: {
          model_name: task.asr_model_name || batch.value?.combinations?.[0]?.asr_model?.name || '-',
          full_transcript: task.full_transcript || '',
          status: task.asr_source || 'pending',
          asr_source: task.asr_source || '-',
        },
        llm: {
          model_name: task.llm_model_name || batch.value?.combinations?.[0]?.llm_model?.name || '-',
          summary_text: task.summary_text || '',
          structured_result: task.structured_result,
          raw_output: task.llm_raw_output || '',
          prompt_template_name: task.prompt_template_name || batch.value?.combinations?.[0]?.prompt_name || '',
          accuracy: task.accuracy,
          status: task.status,
          error_message: task.error_message || '',
          missing_fields: missingFields,
        },
        ground_truth: task.ground_truth || task.patient?.result || {},
        experiment: {
          batch_name: batch.value?.name || '',
          task_status: task.status,
        },
      }
    }

    function openDetail(record: any) {
      if (!record) return
      detailData.value = buildDetailData(record.task)
      detailVisible.value = true
    }

    function handleExport() {
      const url = experimentApi.export(batchId.value)
      window.open(url, '_blank')
    }

    function parseEval(ev: any): any {
      if (!ev) return null
      if (typeof ev === 'string') {
        try { return JSON.parse(ev) } catch { return null }
      }
      return ev
    }

    async function fetchData() {
      try {
        const res = await experimentApi.get(batchId.value)
        batch.value = res?.data || res || null
        if (batch.value) {
          const combo = batch.value.combinations?.[0]
          if (combo) {
            config.prompt_name = combo.prompt_name || ''
            config.has_prompt = !!(combo.prompt_template && combo.prompt_template.length > 0)
            config.asr_model_name = combo.asr_model?.name || ''
            config.llm_model_name = combo.llm_model?.name || ''
          }
          if (!config.prompt_name && batch.value.prompt_template_name) {
            config.prompt_name = batch.value.prompt_template_name
          }
        }
      } catch (e) {
        console.error('fetchData error:', e)
        message.error('加载失败')
      }
    }

    async function fetchProgress() {
      try { progress.value = await experimentApi.progress(batchId.value) } catch {}
    }

    async function fetchTasks() {
      try {
        const res = await experimentApi.tasks(batchId.value)
        tasks.value = Array.isArray(res) ? res : (res.data || [])
      } catch {}
    }

    async function refreshAll() {
      loading.value = true
      try {
        await fetchData()
        await fetchProgress()
        await fetchTasks()
      } finally {
        loading.value = false
      }
    }

    function startPolling() {
      stopPolling()
      pollTimer = setInterval(async () => {
        await fetchData()
        await fetchProgress()
        await fetchTasks()
        const status = batch.value?.status || progress.value?.status
        if (status && status !== 'running') stopPolling()
      }, 2500)
    }

    function stopPolling() {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }

    async function handleStart() {
      try {
        const res = await experimentApi.start(batchId.value)
        const data = (res as any)?.data || res
        message.success(`实验已启动，共 ${data?.total_tasks || 0} 个任务`)
        await refreshAll()
        if (batch.value?.status === 'running') startPolling()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '启动失败')
      }
    }
    async function handlePause() {
      try { await experimentApi.pause(batchId.value); message.success('已暂停'); refreshAll() } catch { message.error('暂停失败') }
    }
    async function handleResume() {
      try { await experimentApi.resume(batchId.value); message.success('已继续'); refreshAll(); startPolling() } catch { message.error('继续失败') }
    }
    async function handleRetryFailed() {
      try { await experimentApi.retry(batchId.value); message.success('已重试失败任务'); refreshAll(); startPolling() } catch { message.error('重试失败') }
    }

    onMounted(async () => {
      await refreshAll()
      if (batch.value?.status === 'running') startPolling()
    })

    onUnmounted(() => { stopPolling() })

    return {
      batch, tasks, loading, progress, config,
      selectedPatientIds, statusColor, canStart,
      recordResults, detailVisible, detailData,
      successCount, failCount,
      refreshAll, handleStart, handlePause, handleResume, handleRetryFailed,
      openDetail, handleExport, symbolFor,
      ArrowLeftOutlined, ReloadOutlined,
    }
  },
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
