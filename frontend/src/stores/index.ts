import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { DateFolder, ModelConfig, DataStatus, PatientExamination, Batch, VerificationResult } from '../types'
import { audioApi, modelApi } from '../api/client'

export const useAppStore = defineStore('app', () => {
  // 录音树
  const audioTree = ref<DateFolder[]>([])
  const dataStatus = ref<DataStatus | null>(null)
  const loadingTree = ref(false)

  // 批次管理
  const batches = ref<Batch[]>([])
  const selectedBatch = ref<string | null>(null)

  // 平铺记录列表（用于表格）
  const records = ref<PatientExamination[]>([])

  // 当前选中的记录（用于抽屉详情）
  const selectedRecord = ref<PatientExamination | null>(null)

  // 抽屉开关
  const drawerOpen = ref(false)

  // 模型配置
  const asrModels = ref<ModelConfig[]>([])
  const llmModels = ref<ModelConfig[]>([])

  // 数据核对
  const verification = ref<VerificationResult | null>(null)
  const verifying = ref(false)

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

  async function fetchBatches() {
    try {
      const data = await audioApi.getBatches()
      batches.value = data as Batch[]
    } catch (e) {
      console.error('fetchBatches error:', e)
    }
  }

  async function fetchRecords() {
    loadingTree.value = true
    try {
      const data = await audioApi.getRecords(selectedBatch.value ?? undefined)
      records.value = data as PatientExamination[]
    } catch (e) {
      console.error('fetchRecords error:', e)
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

  async function fetchVerification() {
    verifying.value = true
    try {
      const data = await audioApi.verify(selectedBatch.value ?? undefined)
      verification.value = data as VerificationResult
    } finally {
      verifying.value = false
    }
  }

  async function deletePatient(patientId: number) {
    await audioApi.deletePatient(patientId)
    await fetchRecords()
    if (verification.value) {
      fetchVerification()
    }
  }

  function selectBatch(date: string | null) {
    selectedBatch.value = date
    fetchRecords()
    if (verification.value) {
      fetchVerification()
    }
  }

  function openDrawer(record: PatientExamination) {
    selectedRecord.value = record
    drawerOpen.value = true
  }

  function closeDrawer() {
    drawerOpen.value = false
    selectedRecord.value = null
  }

  async function fetchModels() {
    const [asr, llm] = await Promise.all([
      modelApi.list('asr'),
      modelApi.list('llm'),
    ])
    asrModels.value = asr as ModelConfig[]
    llmModels.value = llm as ModelConfig[]
  }

  return {
    audioTree, dataStatus, loadingTree,
    batches, selectedBatch,
    records, selectedRecord, drawerOpen,
    asrModels, llmModels,
    verification, verifying,
    fetchAudioTree, fetchBatches, fetchRecords, fetchDataStatus, scanRecordings, fetchModels, fetchVerification, deletePatient, selectBatch, openDrawer, closeDrawer,
  }
})
