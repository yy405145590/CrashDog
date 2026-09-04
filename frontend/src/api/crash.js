import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export function uploadCrash(file, options = {}) {
  const form = new FormData()
  form.append('file', file)
  if (options.remark) {
    form.append('remark', options.remark)
  }
  if (options.resolution_status) {
    form.append('resolution_status', options.resolution_status)
  }
  return api.post('/crashes/upload', form)
}

export function listCrashes(params = {}) {
  return api.get('/crashes', { params })
}

export function getCrash(id) {
  return api.get(`/crashes/${encodeURIComponent(id)}`)
}

export function triggerAnalysis(id, agentType) {
  return api.post(`/crashes/${encodeURIComponent(id)}/analyze`, agentType ? { agent_type: agentType } : {})
}

export function getAnalyses(id) {
  return api.get(`/crashes/${encodeURIComponent(id)}/analysis`)
}

export function getCrashStatus(id) {
  return api.get(`/crashes/${encodeURIComponent(id)}/status`)
}

export function getAnalysisLog(id, offset = 0) {
  return api.get(`/crashes/${encodeURIComponent(id)}/log`, { params: { offset } })
}

export function deleteCrash(id) {
  return api.delete(`/crashes/${encodeURIComponent(id)}`)
}

export function updateCrash(id, payload) {
  return api.patch(`/crashes/${encodeURIComponent(id)}`, payload)
}
