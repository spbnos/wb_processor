const API_KEY = (window as any).__API_KEY__ ?? 'dev-key-change-in-prod'
const BASE = '/api'

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...(opts.headers ?? {}),
    },
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

import type { SystemStats, ReviewItem, MappingItem, TaskResult, ModelVersion, KBStatus } from '../types'

export const api = {
  health:         ()              => req<{status:string;uptime_seconds:number}>('/stats/health'),
  systemStats:    ()              => req<SystemStats>('/stats/system'),
  mappings:       ()              => req<MappingItem[]>('/mappings'),
  deleteMapping:  (id: number)    => req(`/mappings/${id}`, { method: 'DELETE' }),
  reviewItems:    ()              => req<ReviewItem[]>('/review'),
  reviewStats:    ()              => req<{total:number;pending:number;by_status:Record<string,number>}>('/review/stats'),
  approve:        (id: string, field?: string) =>
    req(`/review/${id}/approve`, { method: 'POST', body: JSON.stringify({ field: field ?? null }) }),
  reject:         (id: string, field: string) =>
    req(`/review/${id}/reject`, { method: 'POST', body: JSON.stringify({ correct_field: field }) }),
  uploadFile:     (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return fetch(`${BASE}/files/upload`, {
      method: 'POST', headers: { 'X-API-Key': API_KEY }, body: fd,
    }).then(r => r.json())
  },
  taskStatus:     (id: string)    => req<TaskResult>(`/files/tasks/${id}`),
  mlModels:       ()              => req<string[]>('/ml/models'),
  mlVersions:     (name: string)  => req<ModelVersion[]>(`/ml/models/${name}`),
  mlTrain:        ()              => req('/ml/train', { method: 'POST', body: '{}' }),
  mlFeatureStats: ()              => req<Record<string,unknown>>('/ml/features/stats'),
  kbStatus:       ()              => req<KBStatus>('/kb/status'),
  kbDocuments:    ()              => req<Record<string,unknown>[]>('/kb/documents'),
  kbReindex:      ()              => req('/kb/index', { method: 'POST' }),
  kbField:        (col: string)   => req(`/kb/field?col=${encodeURIComponent(col)}`),
}
