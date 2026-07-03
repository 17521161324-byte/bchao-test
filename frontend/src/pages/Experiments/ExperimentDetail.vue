<template>
  <div class="page-container">
    <div class="page-header">
      <h2>{{ batch?.name || '实验详情' }}</h2>
      <a-space>
        <router-link to="/experiments"><a-button><ArrowLeftOutlined />返回</a-button></router-link>
        <a-button @click="fetchData"><ReloadOutlined />刷新</a-button>
      </a-space>
    </div>

    <!-- 统计卡片 -->
    <a-row :gutter="16" style="margin-bottom: 16px" v-if="batch">
      <a-col :span="4"><a-card><a-statistic title="状态" :value="batch.status" /></a-card></a-col>
      <a-col :span="4"><a-card><a-statistic title="总任务" :value="batch.total_tasks" /></a-card></a-col>
      <a-col :span="4"><a-card><a-statistic title="成功" :value="batch.success_count" :value-style="{ color: '#52c41a' }" /></a-card></a-col>
      <a-col :span="4"><a-card><a-statistic title="失败" :value="batch.failure_count" :value-style="{ color: '#ff4d4f' }" /></a-card></a-col>
      <a-col :span="4"><a-card><a-statistic title="准确率" :value="avgAccuracy" suffix="%" /></a-card></a-col>
    </a-row>

    <!-- 进度条 -->
    <a-card v-if="progress && batch?.status === 'running'" style="margin-bottom: 16px">
      <a-progress :percent="progress.percent" :status="progress.percent >= 100 ? 'success' : 'active'" :format="() => `${progress.success + progress.failed}/${progress.total}`" />
    </a-card>

    <!-- 控制按钮 -->
    <a-space style="margin-bottom: 16px">
      <a-button type="primary" @click="handleStart" :disabled="batch?.status === 'running' || !batch?.combinations?.length">开始实验</a-button>
      <a-button @click="fetchTasks" :loading="loadingTasks">刷新任务</a-button>
      <router-link :to="`/experiments/${batchId}/results`"><a-button>查看对比结果</a-button></router-link>
    </a-space>

    <!-- 组合信息（简化展示） -->
    <a-card v-if="batch?.combinations?.length" size="small" style="margin-bottom: 16px">
      <template #title>实验组合 ({{ batch.combinations.length }})</template>
      <a-row :gutter="8">
        <a-col v-for="combo in batch.combinations" :key="combo.id" :span="6">
          <a-tag color="blue" style="margin-bottom: 4px">
            {{ get_model_name(combo.asr_model_id) }}{{ combo.llm_model_id ? ' + ' + get_model_name(combo.llm_model_id) : '' }}
          </a-tag>
        </a-col>
      </a-row>
    </a-card>

    <!-- 任务列表（按患者分组展示） -->
    <a-card title="患者任务列表">
      <a-spin v-if="loadingTasks" />
      <a-table
        v-else
        :data-source="patientTasks"
        :pagination="{ pageSize: 20, showTotal: (t) => `共 ${t} 位患者` }"
        size="small"
        row-key="record_id"
      >
        <a-table-column title="病历号" data-index="record_id" :width="120" fixed="left" />
        <a-table-column title="日期" data-index="date" :width="120" />
        <a-table-column title="状态" :width="100">
          <template #default="{ record }">
            <a-tag :color="record.all_success ? 'green' : record.has_failed ? 'red' : record.all_pending ? 'default' : 'blue'">
              {{ record.status_label }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column v-for="combo in batch?.combinations || []" :key="combo.id" :title="getComboLabel(combo)" :width="120">
          <template #default="{ record }">
            <a-tag v-if="getTaskStatus(record, combo.id) === 'success'" color="green">✅</a-tag>
            <a-tag v-else-if="getTaskStatus(record, combo.id) === 'failed'" color="red">❌</a-tag>
            <a-tag v-else-if="getTaskStatus(record, combo.id) === 'running'" color="blue">⏳</a-tag>
            <span v-else style="color: #ccc">-</span>
          </template>
        </a-table-column>
        <a-table-column title="最佳准确率" :width="100">
          <template #default="{ record }">
            {{ record.best_accuracy != null ? (record.best_accuracy * 100).toFixed(0) + '%' : '-' }}
          </template>
        </a-table-column>
      </a-table>
    </a-card>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { experimentApi } from '@/api/experiment'
import { modelApi } from '@/api/client'

export default defineComponent({
  name: 'ExperimentDetail',
  setup() {
    const route = useRoute()
    const batchId = computed(() => Number(route.params.id))
    const batch = ref<any>(null)
    const tasks = ref<any[]>([])
    const loadingTasks = ref(false)
    const modelsMap = ref<Record<number, string>>({})
    const progress = ref<any>(null)

    const avgAccuracy = computed(() => {
      const successTasks = tasks.value.filter((t: any) => t.accuracy != null)
      if (!successTasks.length) return 0
      const sum = successTasks.reduce((s: number, t: any) => s + (t.accuracy || 0), 0)
      return Math.round((sum / successTasks.length) * 100)
    })

    async function fetchData() {
      try {
        const res = await experimentApi.get(batchId.value)
        batch.value = res.data
      } catch {
        message.error('加载失败')
      }
    }

    async function fetchTasks() {
      loadingTasks.value = true
      try {
        const res = await experimentApi.tasks(batchId.value)
        tasks.value = res
      } finally {
        loadingTasks.value = false
      }
    }

    // Group tasks by patient
    const patientTasks = computed(() => {
      const map: Record<string, any> = {}
      for (const task of tasks.value) {
        const key = task.record_id
        if (!map[key]) {
          map[key] = {
            record_id: key,
            date: task.date,
            tasks: [],
            all_success: true,
            has_failed: false,
            all_pending: true,
            best_accuracy: null,
          }
        }
        map[key].tasks.push(task)
        if (task.status !== 'success') map[key].all_success = false
        if (task.status === 'failed') map[key].has_failed = true
        if (task.status !== 'pending') map[key].all_pending = false
        if (task.accuracy != null && (map[key].best_accuracy == null || task.accuracy > map[key].best_accuracy)) {
          map[key].best_accuracy = task.accuracy
        }
      }
      // Compute status label
      for (const pt of Object.values(map)) {
        if (pt.all_success) pt.status_label = '全部成功'
        else if (pt.has_failed) pt.status_label = '有失败'
        else if (pt.all_pending) pt.status_label = '待执行'
        else pt.status_label = '执行中'
      }
      return Object.values(map).sort((a: any, b: any) => a.record_id.localeCompare(b.record_id))
    })

    function getTaskStatus(patient: any, comboId: number): string {
      const task = patient.tasks.find((t: any) => t.combination_id === comboId)
      return task?.status || ''
    }

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([modelApi.list('asr'), modelApi.list('llm')])
        const map: Record<number, string> = {}
        for (const m of [...asr, ...llm]) map[m.id] = m.name
        modelsMap.value = map
      } catch { /* ignore */ }
    }

    function get_model_name(id: number): string {
      return modelsMap.value[id] || `#${id}`
    }

    function getComboLabel(combo: any): string {
      const asr = get_model_name(combo.asr_model_id)
      const llm = combo.llm_model_id ? '+' + get_model_name(combo.llm_model_id) : ''
      return asr + llm
    }

    async function handleStart() {
      try {
        await experimentApi.start(batchId.value)
        message.success('实验已启动')
        fetchData()
        fetchTasks()
      } catch {
        message.error('启动失败')
      }
    }

    onMounted(() => {
      fetchData()
      fetchTasks()
      loadModels()
    })

    return {
      batchId, batch, tasks, loadingTasks, progress, patientTasks, avgAccuracy,
      fetchData, fetchTasks, get_model_name, getComboLabel, getTaskStatus, handleStart,
      ArrowLeftOutlined, ReloadOutlined,
    }
  },
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
