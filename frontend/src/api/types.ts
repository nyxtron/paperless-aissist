/** Document summary for the chat document list. */
export interface ChatDocument {
  /** Paperless document ID. */
  id: number
  /** Document title. */
  title: string
  /** ISO timestamp of document creation. */
  created: string
}

/** A single chat message in a document conversation. */
export interface ChatMessage {
  /** Message role: 'user' or 'assistant'. */
  role: 'user' | 'assistant'
  /** Message content text. */
  content: string
}

/** Processing step status entry. */
export interface Step {
  /** Step name identifier. */
  name: string
  /** Step execution status: 'completed', 'failed', etc. */
  status: string
}

/** A custom field as previews and results name it; documentlink values are id lists. */
export interface NamedCustomField {
  id: number
  name: string
  value: string | number | boolean | number[] | null
}

/** Proposed metadata changes from processing. */
export interface ProposedChanges {
  /** Suggested new title, if applicable. */
  title?: string
  /** Suggested correspondent with ID and name. */
  correspondent?: { id: number; name: string }
  /** Suggested document type with ID and name. */
  document_type?: { id: number; name: string }
  /** Suggested tags with IDs and names. */
  tags?: Array<{ id: number; name: string }>
  /** Custom field values with field ID and name; fields already on the document come along. */
  custom_fields?: NamedCustomField[]
  /** Document date the date step found, as YYYY-MM-DD. */
  created_date?: string
  /** Review tag plan, present when a decision step ran. */
  review?: ReviewPlan
}

/** Why a decided field was left unchanged for review. */
export type ReviewReason =
  | 'below_threshold'
  | 'low_mass'
  | 'final_none'
  | 'creation_off'
  | 'none_of_these'
  | 'named_existing'
  | 'no_name_prompt'
  | 'no_name'
  | 'untrusted_response'
  | 'claimed_existing_no_match'
  | 'implausible_name'
  | 'create_failed'

/** Why a field went the text prompt's way instead of being decided. */
export type FallbackReason =
  | 'no_logprobs'
  | 'unsupported_parameter'
  | 'route_missing'
  | 'format_unsupported'
  | 'provider_unsupported'
  | 'url_missing'
  | 'model_missing'
  | 'prompt_inactive'
  | 'empty_list'
  | 'no_letters'
  | 'context_exceeded'

export type DecisionOutcome = 'applied' | 'created' | 'would_create' | 'review' | 'fallback'

/** The fields decision mode can decide. */
export type DecisionField = 'correspondent' | 'document_type'

/** How a field was decided from the Paperless list, or why it was not. */
export interface DecisionDetails {
  method: string
  provider: string
  model: string
  outcome: DecisionOutcome
  reason: ReviewReason | null
  /** A list name, "None of these", or null on a fallback. */
  choice: string | null
  probability: number | null
  threshold: number
  top: Array<{ name: string; p: number }>
  requests: number
  /** Letter mass of the deciding round; null on SystemOne. */
  mass: number | null
  fallback_reason: FallbackReason | null
  fallback_detail: string | null
  /** The deciding request with the text left out; full carries it, preview only. */
  request: { text_chars: number; text_sha256: string; rendered: string | null; full?: string }
  /** The sender the text model named when creating correspondents is off; nothing was created. */
  suggestion?: string
}

/** Whether the review tag goes on or comes off; tag.id is null when the tag is missing. */
export interface ReviewPlan {
  tag: { id: number | null; name: string }
  add_fields: DecisionField[]
  remove: boolean
  missing: boolean
}

/** Result of the decision model test; review_tag.exists is null when Paperless could not be asked. */
export interface DecisionTestResult {
  success: boolean
  method?: string
  model?: string
  choice?: string | null
  probability?: number | null
  fallback_reason?: FallbackReason | null
  fallback_detail?: string | null
  request?: string | null
  /** Set when asking the decision model failed. */
  message?: string
  review_tag?: { name: string; exists: boolean | null }
}

/** Standard API error response shape. */
export interface ApiError {
  /** Error detail message from the server. */
  detail: string
}

/** Result of processing a single document. */
export interface ProcessingPreview {
  /** Whether processing completed without fatal errors. */
  success: boolean
  /** The Paperless document ID that was processed. */
  document_id: number
  /** Error message if processing failed. */
  error?: string
  /** Processing step results. */
  steps: Array<{
    /** Step name. */
    name: string
    /** Step status. */
    status: string
    /** Step execution duration in milliseconds. */
    duration_ms: number
    /** Step error message, if any. */
    error?: string
    /** Step diagnostics; prompt_cut is set when Ollama cut the prompt. */
    details?: {
      prompt_cut?: { evaluated: number; window: number | null }
      decision?: DecisionDetails
      [key: string]: unknown
    }
  }>
  /** Proposed metadata changes from the processing pipeline. */
  proposed_changes: ProposedChanges
}

/** LLM connection test result. */
export interface LlmTestResult {
  /** Whether the overall test succeeded. */
  success: boolean
  /** Main LLM connection test result. */
  main: { success: boolean; message: string; models?: string[] }
  /** Vision LLM connection test result, if applicable. */
  vision: { success: boolean; message: string; models?: string[] } | null
}

/** Scheduler status from the backend. */
export interface SchedulerStatus {
  running: boolean
  interval_minutes: number | null
  next_run: string | null
  is_processing: boolean
  current_document_ids?: number[]
  active_documents?: Array<{
    document_id: number
    trigger_tags?: string[]
    trigger_mode?: string | null
    active_step?: string | null
    started_at?: string | null
    running_seconds?: number | null
    page?: number | null
    pages?: number | null
  }>
  started_at?: string | null
  running_seconds?: number | null
  last_finished_at?: string | null
  stop_requested?: boolean
  last_stop?: {
    reason: string
    failures: number
    at: string
    kind?: 'hand' | 'failures' | 'review_tag'
  } | null
  paperless_url?: string | null
}
