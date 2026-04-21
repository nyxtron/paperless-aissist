import { AxiosError } from 'axios'

/** Structured error information extracted from an API response. */
export interface ExtractedApiError {
  /** HTTP status code, if available. */
  status?: number
  /** Error detail message from the API response. */
  detail?: string
  /** Human-readable error message. */
  message: string
}

/**
 * Extract structured error information from an unknown error value.
 *
 * Handles AxiosError, generic Error, and unknown error types,
 * always returning a consistent ApiError object.
 *
 * @param error - The thrown error value.
 * @returns An ExtractedApiError with status, detail, and message fields.
 */
export function extractApiError(error: unknown): ExtractedApiError {
  if (error instanceof AxiosError) {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    return {
      status,
      detail: detail || error.message,
      message: detail || error.message,
    }
  }
  if (error instanceof Error) {
    return { message: error.message }
  }
  return { message: 'Unknown error' }
}
