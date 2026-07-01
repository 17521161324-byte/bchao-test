<template>
  <div class="page-container">
    <div class="page-header"><h2>单条测试</h2></div>

    <a-row :gutter="16">
      <a-col :span="10">
        <a-card title="测试配置">
          <a-space direction="vertical" style="width: 100%" :size="12">
            <div>
              <span style="color: #666">选择日期：</span>
              <a-select
                style="width: 100%; margin-top: 4px"
                placeholder="选择日期"
                :value="selectedDate"
                @change="handleDateChange"
                :options="audioTree.map((f) => ({ value: f.date, label: f.date }))"
              />
            </div>

            <div>
              <span style="color: #666">选择病历号：</span>
              <a-select
                style="width: 100%; margin-top: 4px"
                placeholder="选择病历号"
                :value="selectedRecord"
                @change="handleRecordChange"
                :disabled="!selectedDate"
                show-search
                :filter-option="(input: string, option: any) => option.label.includes(input)"
                :options="currentPatients.map((p) => ({
                  value: p.record_id,
                  label: `${p.record_id} (${p.segs.length} 段)`,
                  disabled: !p.has_result,
                }))"
              />
            </div>

            <div>
              <span style="color: #666">ASR 模型：</span>
              <a-select
                style="width: 100%; margin-top: 4px"
                placeholder="选择 ASR 模型"
                :value="asrModelId"
                @change="(v: number) => asrModelId = v"
                :options="asrModels.map((m) => ({ value: m.id, label: m.name }))"
              />
            </div>

            <div>
              <span style="color: #666">LLM 模型（可选）：</span>
              <a-select
                style="width: 100%; margin-top: 4px"
                placeholder="选择 LLM 模型"
                :value="llmModelId"
                allow-clear
                @change="(v: number | undefined) => llmModelId = v"
                :options="llmModels.map((m) => ({ value: m.id, label: m.name }))"
              />
            </div>

            <a-button
              type="primary"
              size="large"
              block
              :loading="testing"
              :disabled="!selectedRecord || !asrModelId"
              @click="handleStartTest"
            >
              <PlayCircleOutlined v-if="!testing" />
              <LoadingOutlined v-else />
              {{ testing ? '测试中...' : '开始测试' }}
            </a-button>

            <div v-if="testing">
              <a-progress :percent="getProgressPercent()" status="active" />
              <div style="margin-top: 4px; color: #666; font-size: 12px">
                {{ progress?.message || '正在执行...' }}
                <span v-if="progress?.current && progress?.total">
                  ({{ progress.current }}/{{ progress.total }})
                </span>
              </div>
            </div>
          </a-space>
        </a-card>
      </a-col>

      <a-col :span="14">
        <template v-if="selectedPatient">
          <a-card :title="`录音播放 - ${selectedPatient.record_id}`">
            <AudioPlayer
              :segs="selectedPatient.segs"
              :highlight-seg-index="testing && progress?.stage === 'asr' && progress.current ? progress.current - 1 : undefined"
            />
          </a-card>

          <a-card title="分段转写" style="margin-top: 16px">
            <SegList :segs="selectedPatient.segs" :asr-results="testResult?.asr_results || []" />
          </a-card>

          <a-card v-if="testResult" title="测试结果" style="margin-top: 16px">
            <a-descriptions :column="2" size="small" bordered>
              <a-descriptions-item label="耗时">{{ testResult.duration_seconds }}s</a-descriptions-item>
              <a-descriptions-item label="ASR 段数">{{ testResult.asr_results?.length ?? 0 }}</a-descriptions-item>
            </a-descriptions>

            <div v-if="testResult.summary_text" style="margin-top: 16px">
              <span style="font-weight: bold">总结：</span>
              <div class="summary-box">{{ testResult.summary_text }}</div>
            </div>

            <div v-if="testResult.structured_result" style="margin-top: 16px">
              <span style="font-weight: bold">结构化结果：</span>
              <pre class="code-box">{{ JSON.stringify(testResult.structured_result, null, 2) }}</pre>
            </div>

            <div v-if="testResult.accuracy !== null && testResult.accuracy !== undefined" style="margin-top: 16px">
              <a-tag :color="testResult.accuracy >= 0.8 ? 'green' : testResult.accuracy >= 0.5 ? 'orange' : 'red'">
                准确率: {{ (testResult.accuracy * 100).toFixed(1) }}%
              </a-tag>
            </div>

            <a-collapse v-if="testResult.llm_raw_output" style="margin-top: 16px">
              <a-collapse-panel key="1" header="查看 LLM 原始输出">
                <pre class="code-box">{{ testResult.llm_raw_output }}</pre>
              </a-collapse-panel>
            </a-collapse>
          </a-card>
        </template>

        <a-card v-else>
          <a-empty description="请先选择日期和病历号" />
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlayCircleOutlined, LoadingOutlined,
} from '@ant-design/icons-vue'
import { useAppStore } from '@/stores'
import { testApi, startTestSSE } from '@/api/client'
import type { ModelConfig, TestProgressEvent } from '@/types'
import AudioPlayer from '@/components/AudioPlayer/index.vue'
import SegList from '@/components/SegList/index.vue'

const store = useAppStore()
const { audioTree, asrModels, llmModels, fetchAudioTree, fetchModels } = store

const selectedDate = ref<string | null>(null)
const selectedRecord = ref<string | null>(null)
const selectedPatient = ref<any>(null)
const asrModelId = ref<number | undefined>()
const llmModelId = ref<number | undefined>()

const testing = ref(false)
const progress = ref<TestProgressEvent | null>(null)
const testResult = ref<any>(null)

onMounted(() => {
  fetchAudioTree()
  fetchModels()
})

watch(asrModels, (list) => {
  const defaultAsr = list.find((m) => m.is_default) || list[0]
  if (defaultAsr) asrModelId.value = defaultAsr.id
})

const currentPatients = computed(() => {
  const folder = audioTree.value.find((f) => f.date === selectedDate.value)
  return folder?.patients || []
})

function handleDateChange(date: string) {
  selectedDate.value = date
  selectedRecord.value = null
  selectedPatient.value = null
  testResult.value = null
}

function handleRecordChange(recordId: string) {
  selectedRecord.value = recordId
  const folder = audioTree.value.find((f) => f.date === selectedDate.value)
  selectedPatient.value = folder?.patients.find((p) => p.record_id === recordId)
  testResult.value = null
}

function getProgressPercent(): number {
  if (!progress.value) return 0
  if (progress.value.stage === 'asr' && progress.value.total) {
    return Math.round(((progress.value.current || 0) / progress.value.total) * 100)
  }
  if (progress.value.stage === 'llm') return 95
  if (progress.value.stage === 'complete') return 100
  return 0
}

function handleStartTest() {
  if (!selectedRecord.value || !asrModelId.value) {
    message.warning('请选择病历号和 ASR 模型')
    return
  }

  testing.value = true
  testResult.value = null
  progress.value = { stage: 'asr', message: '准备开始...' }

  const es = startTestSSE({
    record_id: selectedRecord.value,
    asr_model_id: asrModelId.value,
    llm_model_id: llmModelId.value,
    prompt_version: 'v1.0',
  })

  es.addEventListener('progress', (e: MessageEvent) => {
    progress.value = JSON.parse(e.data)
  })

  es.addEventListener('complete', async (e: MessageEvent) => {
    const data = JSON.parse(e.data)
    es.close()
    testing.value = false
    try {
      testResult.value = await testApi.getResult(data.test_id)
      message.success('测试完成')
    } catch {
      message.error('获取结果失败')
    }
  })

  es.addEventListener('error', () => {
    es.close()
    testing.value = false
    message.error('测试执行出错')
  })

  es.onerror = () => {
    es.close()
    testing.value = false
  }
}
</script>

<style scoped>
.summary-box { margin-top: 8px; padding: 12px; background: #f6ffed; border-radius: 4px; }
.code-box { margin-top: 8px; padding: 12px; background: #f5f5f5; border-radius: 4px; font-size: 12px; max-height: 300px; overflow: auto; }
</style>
