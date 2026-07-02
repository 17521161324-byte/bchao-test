import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { DateFolder, ModelConfig, DataStatus, PatientGroup, PatientExamination, Batch, VerificationResult } from '../types'
import { audioApi, modelApi } from '../api/client'

export const useAppStore = defineStore('app', () => {
  // 录音树
  const audioTree = ref<DateFolder[]>([])
  const dataStatus = ref<DataStatus | null>(null)
  const loadingTree = ref(false)

  // 批次管理
  const batches = ref<Batch[]>([])
  const selectedBatch = ref<string | null>(null)

  // 患者列表（新）
  const patientGroups = ref<PatientGroup[]>([])
  const selectedGroup = ref<PatientGroup | null>(null)
  const selectedExam = ref<PatientExamination | null>(null)

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

  async function fetchBatches() {
    try {
      const data = await audioApi.getBatches()
      batches.value = data as Batch[]
    } catch (e) {
      console.error('fetchBatches error:', e)
    }
  }

  async function fetchPatients() {
    loadingTree.value = true
    try {
      const data = await audioApi.getPatients(selectedBatch.value ?? undefined)
      patientGroups.value = data as PatientGroup[]
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

  // 数据核对
  const verification = ref<VerificationResult | null>(null)
  const verifying = ref(false)

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
    // Refresh both lists
    await fetchPatients()
    await fetchVerification()
  }

  function selectBatch(date: string | null) {
    selectedBatch.value = date
    fetchPatients()
    if (verification.value) {
      fetchVerification()
    }
  }

  function selectExam(group: PatientGroup, exam: PatientExamination) {
    selectedGroup.value = group
    selectedExam.value = exam
    selectedRecord.value = exam.record_id
    selectedDate.value = exam.date
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
    batches, selectedBatch,
    patientGroups, selectedGroup, selectedExam,
    verification, verifying,
    asrModels, llmModels,
    selectedRecord, selectedDate,
    fetchAudioTree, fetchBatches, fetchPatients, fetchDataStatus, scanRecordings, fetchModels, fetchVerification, deletePatient, setSelectedRecord, selectBatch, selectExam,
  }
})
