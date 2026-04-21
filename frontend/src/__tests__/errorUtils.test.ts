import { describe, it, expect } from 'vitest'
import { AxiosError } from 'axios'
import { extractApiError } from '../api/errorUtils'

describe('extractApiError', () => {
  it('extracts status and detail from AxiosError', () => {
    const error = new AxiosError(
      'Request failed',
      undefined,
      undefined,
      {},
      {
        status: 404,
        data: { detail: 'Not found' },
        headers: {},
        config: {} as any,
        statusText: 'Not Found',
      },
    )
    const result = extractApiError(error)
    expect(result.status).toBe(404)
    expect(result.detail).toBe('Not found')
    expect(result.message).toBe('Not found')
  })

  it('falls back to error message when no detail in response', () => {
    const error = new AxiosError(
      'Connection failed',
      undefined,
      undefined,
      {},
      {
        status: 0,
        data: {},
        headers: {},
        config: {} as any,
        statusText: '',
      },
    )
    const result = extractApiError(error)
    expect(result.status).toBe(0)
    expect(result.detail).toBe('Connection failed')
    expect(result.message).toBe('Connection failed')
  })

  it('handles generic Error objects', () => {
    const error = new Error('Something went wrong')
    const result = extractApiError(error)
    expect(result.status).toBeUndefined()
    expect(result.detail).toBeUndefined()
    expect(result.message).toBe('Something went wrong')
  })

  it('handles unknown error types', () => {
    const error = { code: 'ERR_UNKNOWN', reason: 'unknown' }
    const result = extractApiError(error)
    expect(result.status).toBeUndefined()
    expect(result.detail).toBeUndefined()
    expect(result.message).toBe('Unknown error')
  })

  it('handles null', () => {
    const result = extractApiError(null)
    expect(result.status).toBeUndefined()
    expect(result.detail).toBeUndefined()
    expect(result.message).toBe('Unknown error')
  })
})
