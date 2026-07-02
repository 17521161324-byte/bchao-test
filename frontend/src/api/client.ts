/**
 * API 客户端封装
 */
import axios, { AxiosInstance } from 'axios'
import { message } from 'ant-design-vue'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const client: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.detail || error.message || '请求失败'
    message.error(msg)
    return Promise.reject(error)
  }
)

// ========== 录音管理 ==========
export const audioApi = {
  getTree: () => client.get('/audio/tree'),
  getBatches: () => client.get('/audio/batches'),
  getPatients: (date?: string) => client.get('/audio/patients', { params: date ? { date } : {} }),
  getStatus: () => client.get('/audio/status'),
  verify: (date?: string) => client.get('/audio/verify', { params: date ? { date } : {} }),
  deletePatient: (patientId: number) => client.delete(`/audio/patient/${patientId}`),
  scan: () => client.post('/audio/scan'),
  getFileUrl: (path: string) => `${API_BASE}/audio/file?path=${encodeURIComponent(path)}`,
}

// ========== 结果管理 ==========
export const resultApi = {
  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/result/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
  getByRecord: (recordId: string) => client.get(`/result/${recordId}`),
  update: (resultId: number, data: any) => client.put(`/result/${resultId}`, data),
}

// ========== 模型配置 ==========
export const modelApi = {
  list: (modelType?: string) => client.get('/model', { params: { model_type: modelType } }),
  create: (data: any) => client.post('/model', data),
  update: (id: number, data: any) => client.put(`/model/${id}`, data),
  delete: (id: number) => client.delete(`/model/${id}`),
  test: (id: number) => client.post(`/model/${id}/test`),
  initDefaults: () => client.post('/model/init-defaults'),
}

// ========== 测试执行 ==========
export const testApi = {
  getHistory: (params?: any) => client.get('/test/history', { params }),
  getResult: (testId: number) => client.get(`/test/${testId}`),
  updateEval: (testId: number, data: any) => client.put(`/test/${testId}/evaluate`, data),
}

// SSE 测试执行
export function startTestSSE(data: {
  record_id: string
  asr_model_id: number
  llm_model_id?: number
  prompt_version?: string
}): EventSource {
  const params = new URLSearchParams()
  params.set('record_id', data.record_id)
  params.set('asr_model_id', String(data.asr_model_id))
  if (data.llm_model_id) params.set('llm_model_id', String(data.llm_model_id))
  if (data.prompt_version) params.set('prompt_version', data.prompt_version)

  const url = `${API_BASE}/test/start?${params.toString()}`
  return new EventSource(url)
}

export default client
