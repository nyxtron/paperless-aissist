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
  /** Suggested custom field values. */
  custom_fields?: Array<{ field: number; value: string }>
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
  current_doc_id: number | null
}
