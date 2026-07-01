/**
 * 全局状态管理
 */
import { create } from 'zustand'
import { DateFolder, ModelConfig, DataStatus } from '../types'
import { audioApi, modelApi } from '../api/client'

interface AppState {
  // 录音树
  audioTree: DateFolder[]
  dataStatus: DataStatus | null
  loadingTree: boolean

  // 模型配置
  asrModels: ModelConfig[]
  llmModels: ModelConfig[]

  // 当前选中的病历号
  selectedRecord: string | null
  selectedDate: string | null

  // Actions
  fetchAudioTree: () => Promise<void>
  fetchDataStatus: () => Promise<void>
  scanRecordings: () => Promise<void>
  fetchModels: () => Promise<void>
  setSelectedRecord: (recordId: string | null, date: string | null) => void
}

export const useAppStore = create<AppState>((set, get) => ({
  audioTree: [],
  dataStatus: null,
  loadingTree: false,
  asrModels: [],
  llmModels: [],
  selectedRecord: null,
  selectedDate: null,

  fetchAudioTree: async () => {
    set({ loadingTree: true })
    try {
      const data = await audioApi.getTree()
      set({ audioTree: data as DateFolder[] })
    } finally {
      set({ loadingTree: false })
    }
  },

  fetchDataStatus: async () => {
    const data = await audioApi.getStatus()
    set({ dataStatus: data as DataStatus })
  },

  scanRecordings: async () => {
    await audioApi.scan()
    await get().fetchAudioTree()
    await get().fetchDataStatus()
  },

  fetchModels: async () => {
    const [asr, llm] = await Promise.all([
      modelApi.list('asr'),
      modelApi.list('llm'),
    ])
    set({ asrModels: asr as ModelConfig[], llmModels: llm as ModelConfig[] })
  },

  setSelectedRecord: (recordId, date) => set({ selectedRecord: recordId, selectedDate: date }),
}))
