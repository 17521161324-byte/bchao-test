/**
 * Experiment API client
 */
import axios from 'axios';

const client = axios.create({ baseURL: '/api' });

export const experimentApi = {
  list: () => client.get('/experiments'),
  get: (id: number) => client.get(`/experiments/${id}`),
  create: (data: any) => client.post('/experiments', data),
  addCombination: (id: number, data: any) => client.post(`/experiments/${id}/combinations`, data),
  updatePatients: (id: number, data: any) => client.put(`/experiments/${id}/patients`, data),
  start: (id: number) => client.post(`/experiments/${id}/start`),
  pause: (id: number) => client.post(`/experiments/${id}/pause`),
  resume: (id: number) => client.post(`/experiments/${id}/resume`),
  cancel: (id: number) => client.post(`/experiments/${id}/cancel`),
  retry: (id: number) => client.post(`/experiments/${id}/retry`),
  tasks: (id: number, status?: string) => client.get(`/experiments/${id}/tasks`, { params: status ? { status } : {} }),
  metrics: (id: number) => client.get(`/experiments/${id}/metrics`),
  results: (id: number) => client.get(`/experiments/${id}/results`),
};
