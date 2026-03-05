import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
});

export const configApi = {
  getAll: () => api.get('/config'),
  get: (key: string) => api.get(`/config/${key}`),
  set: (key: string, value: string, description?: string) => 
    api.post('/config', null, { params: { key, value, description } }),
  delete: (key: string) => api.delete(`/config/${key}`),
};

export const promptsApi = {
  getAll: () => api.get('/prompts'),
  get: (id: number) => api.get(`/prompts/${id}`),
  create: (data: {
    name: string;
    prompt_type: string;
    document_type_filter?: string;
    system_prompt: string;
    user_template: string;
    is_active: boolean;
  }) => api.post('/prompts', data),
  update: (id: number, data: Partial<{
    name: string;
    prompt_type: string;
    document_type_filter: string;
    system_prompt: string;
    user_template: string;
    is_active: boolean;
  }>) => api.put(`/prompts/${id}`, data),
  delete: (id: number) => api.delete(`/prompts/${id}`),
  getTemplates: () => api.get('/prompts/templates'),
  loadSamples: () => api.post('/prompts/load-samples'),
};

export const documentsApi = {
  process: (docId: number) => api.post(`/documents/process/${docId}`),
  trigger: () => api.post('/documents/trigger'),
  testConnection: () => api.get('/documents/test-connection'),
  getTagged: () => api.get('/documents/tagged'),
  getTags: () => api.get('/documents/tags'),
  getChatList: () => api.get('/documents/chat-list'),
  getChatDocument: (docId: number) => api.get(`/documents/chat/${docId}`),
  chat: (docId: number, message: string) => 
    api.post(`/documents/chat?doc_id=${docId}`, null, { params: { message } }),
};

export const statsApi = {
  get: () => api.get('/stats'),
  getDaily: (days?: number) => api.get('/stats/daily', { params: { days } }),
  getRecent: (limit?: number) => api.get('/stats/recent', { params: { limit } }),
  reset: () => api.delete('/stats/reset'),
};

export const schedulerApi = {
  getStatus: () => api.get('/scheduler'),
  start: (intervalMinutes?: number) => api.post('/scheduler/start', null, { params: { interval_minutes: intervalMinutes } }),
  stop: () => api.post('/scheduler/stop'),
  update: (intervalMinutes: number) => api.post('/scheduler/update', null, { params: { interval_minutes: intervalMinutes } }),
  triggerNow: () => api.post('/scheduler/trigger-now'),
  clearState: () => api.post('/scheduler/clear-state'),
};

export default api;
