import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export function uploadSymbol(file, metadata, onProgress) {
  const form = new FormData()
  form.append('file', file)
  if (metadata.game_name) form.append('game_name', metadata.game_name)
  if (metadata.build_version) form.append('build_version', metadata.build_version)
  form.append('platform', metadata.platform || 'Windows')
  if (metadata.svn_revision) form.append('svn_revision', metadata.svn_revision)
  if (metadata.description) form.append('description', metadata.description)
  return api.post('/symbols/upload', form, {
    onUploadProgress: onProgress,
    timeout: 0,
  })
}

export function listSymbols(params = {}) {
  return api.get('/symbols', { params })
}

export function getSymbol(id) {
  return api.get(`/symbols/${encodeURIComponent(id)}`)
}

export function deleteSymbol(id) {
  return api.delete(`/symbols/${encodeURIComponent(id)}`)
}

export function resymbolicate(crashId, symbolPackageId) {
  const params = symbolPackageId ? { symbol_package_id: symbolPackageId } : {}
  return api.post(`/crashes/${encodeURIComponent(crashId)}/resymbolicate`, null, { params })
}
