/**
 * 提示词模版 API
 */
import axios from 'axios'

const c = axios.create({ baseURL: '/api' })

export const promptApi = {
  list: () => c.get('/prompt-templates'),
  get: (id: number) => c.get(`/prompt-templates/${id}`),
  create: (data: any) => c.post('/prompt-templates', data),
  update: (id: number, data: any) => c.put(`/prompt-templates/${id}`, data),
  delete: (id: number) => c.delete(`/prompt-templates/${id}`),
  initDefaults: () => c.post('/prompt-templates/init-defaults'),
}
