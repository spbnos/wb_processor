export interface SystemStats {
  mappings: { total: number; active: number; by_category: Record<string, number> }
  review_queue: { total: number; pending: number; by_status: Record<string, number> }
  redis_queues: Record<string, number>
}
export interface ReviewItem {
  id: string; struct_hash: string; source_column: string
  suggested_field: string | null; suggested_type: string
  confidence_score: number; confidence_level: string
  match_method: string; runner_up_field: string | null; runner_up_score: number
  filepath: string; filename: string; status: string
  created_at: string; sample_values: string[]
  correct_field?: string | null; resolved_by?: string | null
}
export interface MappingItem {
  id: number; name: string; category: string
  subcategory: string | null; columns: number; active: boolean; struct_hash: string
}
export interface TaskResult {
  task_id: string; status: string; result: Record<string, unknown> | null
  error: string | null; created_at: string; completed_at: string | null
}
export interface ModelVersion {
  model_name: string; version: string; status: string
  metrics: Record<string, number>; training_samples: number; trained_at: string
}
export interface KBStatus {
  documents_dir: string
  available_pdfs: number
  loaded_pdfs: number
  indexed_terms: number
  registry_fields: number
  analytics_fields: number
}
