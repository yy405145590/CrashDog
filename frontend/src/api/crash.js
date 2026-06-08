import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export function uploadCrash(file) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/crashes/upload', form)
}

export function listCrashes() {
  return api.get('/crashes')
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
