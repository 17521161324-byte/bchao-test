<template>
  <div class="page-container">
    <div class="page-header">
      <h2>{{ batch?.name || '实验详情' }}</h2>
      <a-space>
        <router-link to="/experiments">
          <a-button><ArrowLeftOutlined />返回</a-button>
        </router-link>
        <a-button @click="fetchData"><ReloadOutlined />刷新</a-button>
      </a-space>
    </div>

    <!-- 统计卡片 -->
    <a-row :gutter="16" style="margin-bottom: 16px" v-if="batch">
      <a-col :span="6"><a-card><a-statistic title="状态" :value="batch.status" /></a-card></a-col>
      <a-col :span="6"><a-card><a-statistic title="总任务" :value="batch.total_tasks" /></a-card></a-col>
      <a-col :span="6"><a-card><a-statistic title="成功" :value="batch.success_count" :value-style="{ color: '#52c41a' }" /></a-card></a-col>
      <a-col :span="6"><a-card><a-statistic title="失败" :value="batch.failure_count" :value-style="{ color: '#ff4d4f' }" /></a-card></a-col>
    </a-row>

    <!-- 进度条 -->
    <a-card v-if="progress && batch?.status === 'running'" style="margin-bottom: 16px">
      <a-progress
        :percent="progress.percent"
        :status="progress.percent >= 100 ? 'success' : 'active'"
        :format="() => `${progress.success + progress.failed}/${progress.total}`"
      />
      <div style="margin-top: 8px; color: #666; font-size: 12px">
        运行中: {{ progress.running }} | 待执行: {{ progress.pending }} | 成功: {{ progress.success }} | 失败: {{ progress.failed }}
      </div>
    </a-card>

    <!-- 控制按钮 -->
    <a-space style="margin-bottom: 16px">
      <a-button type="primary" @click="handleStart" :disabled="batch?.status === 'running' || !batch?.combinations?.length">启动</a-button>
      <a-button @click="handlePause" :disabled="batch?.status !== 'running'">暂停</a-button>
      <a-button @click="handleResume" :disabled="batch?.status !== 'paused'">继续</a-button>
      <a-button danger @click="handleCancel" :disabled="['completed', 'cancelled'].includes(batch?.status || '')">取消</a-button>
      <a-button @click="handleRetry" :disabled="!batch?.failure_count">重试失败</a-button>
      <router-link :to="`/experiments/${batchId}/results`"><a-button>查看结果</a-button></router-link>
    </a-space>

    <!-- 实验组合管理 -->
    <a-card title="实验组合">
      <template #extra>
        <a-button type="primary" size="small" @click="showAddComboModal"><PlusOutlined />添加组合</a-button>
      </template>

      <a-table
        :data-source="batch?.combinations || []"
        :pagination="false"
        size="small"
        row-key="id"
      >
        <a-table-column title="ASR模型" :width="150">
          <template #default="{ record }">
            {{ get_model_name(record.asr_model_id) }}
          </template>
        </a-table-column>
        <a-table-column title="LLM模型" :width="150">
          <template #default="{ record }">
            {{ get_model_name(record.llm_model_id) || '-' }}
          </template>
        </a-table-column>
        <a-table-column title="提示词" data-index="prompt_name" :width="120" />
        <a-table-column title="热词" :width="150">
          <template #default="{ record }">
            <a-tag v-for="h in (record.hotwords || [])" :key="h" size="small">{{ h }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="启用" :width="60">
          <template #default="{ record }">
            <a-switch :checked="record.enabled" @change="toggleEnabled(record)" size="small" />
          </template>
        </a-table-column>
        <a-table-column title="操作" :width="80">
          <template #default="{ record }">
            <a-button size="small" type="link" danger @click="handleDeleteCombo(record.id)">删除</a-button>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <!-- 添加组合弹窗 -->
    <a-modal v-model:open="comboModalOpen" title="添加实验组合" @ok="handleAddCombo" :confirm-loading="comboSaving">
      <a-form layout="vertical" size="small">
        <a-form-item label="ASR模型" required>
          <a-select v-model:value="comboForm.asr_model_id" placeholder="选择ASR模型" style="width: 100%">
            <a-select-option v-for="m in asrModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="LLM模型">
          <a-select v-model:value="comboForm.llm_model_id" placeholder="可选" allow-clear style="width: 100%">
            <a-select-option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.name }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="提示词名称">
          <a-input v-model:value="comboForm.prompt_name" placeholder="如: v1.0" />
        </a-form-item>
        <a-form-item label="提示词模板">
          <a-textarea v-model:value="comboForm.prompt_template" :rows="4" placeholder="输入提示词模板，使用 {transcript} 作为占位符" />
        </a-form-item>
        <a-form-item label="热词（每行一个）">
          <a-textarea v-model:value="comboForm.hotwords_raw" :rows="3" placeholder="如:&#10;卵泡&#10;内膜" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined, ArrowLeftOutlined } from '@ant-design/icons-vue'
import { experimentApi } from '@/api/experiment'
import { modelApi } from '@/api/client'

export default defineComponent({
  name: 'ExperimentDetail',
  setup() {
    const route = useRoute()
    const batchId = computed(() => Number(route.params.id))
    const batch = ref<any>(null)
    const progress = ref<any>(null)
    const asrModels = ref<any[]>([])
    const llmModels = ref<any[]>([])
    const modelsMap = ref<Record<number, string>>({})

    const comboModalOpen = ref(false)
    const comboSaving = ref(false)
    const comboForm = ref({
      asr_model_id: undefined as number | undefined,
      llm_model_id: undefined as number | undefined,
      prompt_name: '',
      prompt_template: '{transcript}',
      hotwords_raw: '',
    })

    let progressTimer: ReturnType<typeof setInterval> | null = null

    async function fetchData() {
      try {
        const res = await experimentApi.get(batchId.value)
        batch.value = res.data
      } catch {
        message.error('加载失败')
      }
    }

    async function fetchProgress() {
      try {
        const res = await experimentApi.progress(batchId.value)
        progress.value = res.data
        // Stop polling if completed/failed/cancelled
        if (['completed', 'cancelled', 'partial'].includes(res.data.status)) {
          stopProgressPolling()
        }
      } catch {
        // ignore
      }
    }

    function startProgressPolling() {
      stopProgressPolling()
      progressTimer = setInterval(fetchProgress, 3000)
    }

    function stopProgressPolling() {
      if (progressTimer) {
        clearInterval(progressTimer)
        progressTimer = null
      }
    }

    async function loadModels() {
      try {
        const [asr, llm] = await Promise.all([
          modelApi.list('asr'),
          modelApi.list('llm'),
        ])
        asrModels.value = asr.data
        llmModels.value = llm.data
        const map: Record<number, string> = {}
        for (const m of [...asr.data, ...llm.data]) map[m.id] = m.name
        modelsMap.value = map
      } catch {
        // ignore
      }
    }

    function get_model_name(id: number): string {
      return modelsValue[id] || `#${id}`
    }

    const modelsValue = computed(() => modelsMap.value)

    async function handleStart() {
      try {
        const res = await experimentApi.start(batchId.value)
        message.success(`实验已启动，共 ${res.data.total_tasks} 个任务`)
        fetchData()
        startProgressPolling()
      } catch {
        message.error('启动失败')
      }
    }

    async function handlePause() {
      await experimentApi.pause(batchId.value)
      message.success('已暂停')
      fetchData()
    }

    async function handleResume() {
      await experimentApi.resume(batchId.value)
      message.success('已继续')
      fetchData()
      startProgressPolling()
    }

    async function handleCancel() {
      await experimentApi.cancel(batchId.value)
      message.success('已取消')
      fetchData()
      stopProgressPolling()
    }

    async function handleRetry() {
      const res = await experimentApi.retry(batchId.value)
      message.success(`已重试 ${res.data.retried} 个失败任务`)
      fetchData()
      startProgressPolling()
    }

    async function toggleEnabled(record: any) {
      try {
        await experimentApi.updateCombination(batchId.value, record.id, { enabled: !record.enabled })
        fetchData()
      } catch {
        message.error('更新失败')
      }
    }

    function showAddComboModal() {
      comboForm.value = {
        asr_model_id: undefined,
        llm_model_id: undefined,
        prompt_name: '',
        prompt_template: '{transcript}',
        hotwords_raw: '',
      }
      comboModalOpen.value = true
    }

    async function handleAddCombo() {
      if (!comboForm.value.asr_model_id) {
        message.error('请选择ASR模型')
        return
      }
      comboSaving.value = true
      try {
        await experimentApi.addCombination(batchId.value, {
          asr_model_id: comboForm.value.asr_model_id,
          llm_model_id: comboForm.value.llm_model_id || null,
          prompt_name: comboForm.value.prompt_name || 'default',
          prompt_template: comboForm.value.prompt_template,
          hotwords: comboForm.value.hotwords_raw.split('\n').filter(Boolean),
        })
        message.success('添加成功')
        comboModalOpen.value = false
        fetchData()
      } catch {
        message.error('添加失败')
      } finally {
        comboSaving.value = false
      }
    }

    async function handleDeleteCombo(comboId: number) {
      try {
        await experimentApi.deleteCombination(batchId.value, comboId)
        message.success('删除成功')
        fetchData()
      } catch {
        message.error('删除失败')
      }
    }

    onMounted(() => {
      fetchData()
      fetchProgress()
      loadModels()
    })

    onUnmounted(() => {
      stopProgressPolling()
    })

    return {
      batchId, batch, progress, asrModels, llmModels,
      comboModalOpen, comboSaving, comboForm,
      fetchData, get_model_name, modelsValue,
      handleStart, handlePause, handleResume, handleCancel, handleRetry,
      toggleEnabled, showAddComboModal, handleAddCombo, handleDeleteCombo,
      PlusOutlined, ReloadOutlined, ArrowLeftOutlined,
    }
  },
})
</script>

<style scoped>
.page-container { padding: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
