/**
 * Pinia 全局状态管理
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { DateFolder, ModelConfig, DataStatus } from '../types'
import { audioApi, modelApi } from '../api/client'

export const useAppStore = defineStore('app', () => {
  // 录音树
  const audioTree = ref<DateFolder[]>([])
  const dataStatus = ref<DataStatus | null>(null)
  const loadingTree = ref(false)

  // 模型配置
  const asrModels = ref<ModelConfig[]>([])
  const llmModels = ref<ModelConfig[]>([])

  // 当前选中的病历号
  const selectedRecord = ref<string | null>(null)
  const selectedDate = ref<string | null>(null)

  // Actions
  async function fetchAudioTree() {
    loadingTree.value = true
    try {
      const data = await audioApi.getTree()
      audioTree.value = data as DateFolder[]
    } finally {
      loadingTree.value = false
    }
  }

  async function fetchDataStatus() {
    const data = await audioApi.getStatus()
    dataStatus.value = data as DataStatus
  }

  async function scanRecordings() {
    await audioApi.scan()
    await fetchAudioTree()
    await fetchDataStatus()
  }

  async function fetchModels() {
    const [asr, llm] = await Promise.all([
      modelApi.list('asr'),
      modelApi.list('llm'),
    ])
    asrModels.value = asr as ModelConfig[]
    llmModels.value = llm as ModelConfig[]
  }

  function setSelectedRecord(recordId: string | null, date: string | null) {
    selectedRecord.value = recordId
    selectedDate.value = date
  }

  return {
    audioTree, dataStatus, loadingTree,
    asrModels, llmModels,
    selectedRecord, selectedDate,
    fetchAudioTree, fetchDataStatus, scanRecordings, fetchModels, setSelectedRecord,
  }
})
