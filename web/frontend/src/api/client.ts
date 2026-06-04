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

export const getMcpStatus = () =>
  api.get('/mcp/status').then(r => r.data)

export const getMcpTools = () =>
  api.get('/mcp/tools').then(r => r.data)

export const connectMcpServer = (name: string) =>
  api.post(`/mcp/connect/${name}`).then(r => r.data)

export const disconnectMcpServer = (name: string) =>
  api.post(`/mcp/disconnect/${name}`).then(r => r.data)

export const toggleMcp = (enabled: boolean) =>
  api.post('/mcp/toggle', null, { params: { enabled } }).then(r => r.data)

// Feishu
export const getFeishuStatus = () =>
  api.get('/feishu/status').then(r => r.data)

export const testFeishuConnection = () =>
  api.post('/feishu/test-connection').then(r => r.data)

export const getFeishuDocuments = (folderToken?: string) =>
  api.get('/feishu/documents', { params: folderToken ? { folder_token: folderToken } : {} }).then(r => r.data)

export const getFeishuBitables = () =>
  api.get('/feishu/bitables').then(r => r.data)

export const deleteFeishuDocument = (fileToken: string, fileType: string) =>
  api.delete(`/feishu/documents/${fileToken}`, { params: { file_type: fileType } }).then(r => r.data)

export default api
