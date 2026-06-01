import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const getConfig = (module?: string) =>
  api.get(module ? `/config/${module}` : '/config').then(r => r.data)

export const updateConfig = (module: string, data: any) =>
  api.put(`/config/${module}`, data).then(r => r.data)

export const testLLM = (data: { provider: string; api_key: string; base_url: string; model: string }) =>
  api.post('/config/test-llm', data).then(r => r.data)

export const testLLMCurrent = () =>
  api.post('/config/test-llm-current').then(r => r.data)

export const getStatus = () => api.get('/status').then(r => r.data)

export const startService = () => api.post('/service/start').then(r => r.data)

export const stopService = () => api.post('/service/stop').then(r => r.data)

export const restartService = () => api.post('/service/restart').then(r => r.data)

export const getStats = () => api.get('/stats').then(r => r.data)

export const getLogs = (params?: { lines?: number; key_only?: boolean }) =>
  api.get('/logs', { params }).then(r => r.data)

export const generateSkill = (data: { description: string }) =>
  api.post('/skills/generate', data).then(r => r.data)

export default api
