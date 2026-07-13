/**
 * Experiment API client
 */
import client from './client';

export const experimentApi = {
  list: () => client.get('/experiments'),
  get: (id: number) => client.get(`/experiments/${id}`),
  create: (data: any) => client.post('/experiments', data),
  delete: (id: number) => client.delete(`/experiments/${id}`),
  addCombination: (id: number, data: any) => client.post(`/experiments/${id}/combinations`, data),
  updateCombination: (batchId: number, comboId: number, data: any) => client.put(`/experiments/${batchId}/combinations/${comboId}`, data),
  deleteCombination: (batchId: number, comboId: number) => client.delete(`/experiments/${batchId}/combinations/${comboId}`),
  updatePatients: (id: number, data: any) => client.put(`/experiments/${id}/patients`, data),
  start: (id: number) => client.post(`/experiments/${id}/start`),
  pause: (id: number) => client.post(`/experiments/${id}/pause`),
  resume: (id: number) => client.post(`/experiments/${id}/resume`),
  cancel: (id: number) => client.post(`/experiments/${id}/cancel`),
  retry: (id: number) => client.post(`/experiments/${id}/retry`),
  progress: (id: number) => client.get(`/experiments/${id}/progress`),
  tasks: (id: number, status?: string) => client.get(`/experiments/${id}/tasks`, { params: status ? { status } : {} }),
  metrics: (id: number) => client.get(`/experiments/${id}/metrics`),
  results: (id: number) => client.get(`/experiments/${id}/results`),
  export: (id: number) => `/api/experiments/${id}/export`,
};
