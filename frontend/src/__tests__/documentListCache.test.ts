import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  clearDocumentListCache,
  getCachedDocumentList,
  getDocumentListStamp,
  invalidateDocumentListCache,
  loadCachedDocumentList,
  setCachedDocumentList,
} from '../utils/documentListCache'

describe('documentListCache', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-16T10:00:00Z'))
    clearDocumentListCache()
  })

  afterEach(() => {
    vi.useRealTimers()
    clearDocumentListCache()
  })

  it('caches loaded data for one hour', async () => {
    const fetcher = vi.fn().mockResolvedValue([{ id: 1 }])

    const first = await loadCachedDocumentList('processing', fetcher)
    const second = await loadCachedDocumentList('processing', fetcher)

    expect(first).toEqual([{ id: 1 }])
    expect(second).toEqual([{ id: 1 }])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('reloads after the cache ttl expires', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce([{ id: 1 }])
      .mockResolvedValueOnce([{ id: 2 }])

    await loadCachedDocumentList('chat', fetcher)
    vi.advanceTimersByTime(60 * 60 * 1000 + 1)
    const result = await loadCachedDocumentList('chat', fetcher)

    expect(result).toEqual([{ id: 2 }])
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('reuses an in-flight request for the same key', async () => {
    let resolveFetcher: (value: Array<{ id: number }>) => void = () => undefined
    const fetcher = vi.fn(
      () => new Promise<Array<{ id: number }>>((resolve) => {
        resolveFetcher = resolve
      }),
    )

    const first = loadCachedDocumentList('processing', fetcher)
    const second = loadCachedDocumentList('processing', fetcher)

    resolveFetcher([{ id: 3 }])

    await expect(first).resolves.toEqual([{ id: 3 }])
    await expect(second).resolves.toEqual([{ id: 3 }])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('force reload bypasses fresh cache when no request is in flight', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce([{ id: 1 }])
      .mockResolvedValueOnce([{ id: 2 }])

    await loadCachedDocumentList('processing', fetcher)
    const result = await loadCachedDocumentList('processing', fetcher, { force: true })

    expect(result).toEqual([{ id: 2 }])
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('force reload reuses an in-flight request for the same key', async () => {
    let resolveFetcher: (value: Array<{ id: number }>) => void = () => undefined
    const fetcher = vi.fn(
      () => new Promise<Array<{ id: number }>>((resolve) => {
        resolveFetcher = resolve
      }),
    )

    const first = loadCachedDocumentList('chat', fetcher)
    const second = loadCachedDocumentList('chat', fetcher, { force: true })

    resolveFetcher([{ id: 4 }])

    await expect(first).resolves.toEqual([{ id: 4 }])
    await expect(second).resolves.toEqual([{ id: 4 }])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('returns cached data while fresh', async () => {
    const fetcher = vi.fn().mockResolvedValue([{ id: 1 }])

    await loadCachedDocumentList('chat', fetcher)

    expect(getCachedDocumentList('chat')).toEqual([{ id: 1 }])
  })

  it('invalidates a single key', async () => {
    const fetcher = vi.fn().mockResolvedValue([{ id: 1 }])

    await loadCachedDocumentList('chat', fetcher)
    invalidateDocumentListCache('chat')

    expect(getCachedDocumentList('chat')).toBeNull()
  })

  it('updates cached data without fetching', () => {
    setCachedDocumentList('processing', [{ id: 2 }])

    expect(getCachedDocumentList('processing')).toEqual([{ id: 2 }])
  })

  it('remembers the stamp the copy was taken under', async () => {
    expect(getDocumentListStamp('processing')).toBeNull()

    await loadCachedDocumentList('processing', async () => [{ id: 1 }], {
      stamp: '2026-09-12T10:00:00+00:00',
    })
    expect(getDocumentListStamp('processing')).toBe('2026-09-12T10:00:00+00:00')

    // Pruning the list in place keeps the stamp; a reload without one clears it.
    setCachedDocumentList('processing', [])
    expect(getDocumentListStamp('processing')).toBe('2026-09-12T10:00:00+00:00')
    await loadCachedDocumentList('processing', async () => [{ id: 2 }], { force: true })
    expect(getDocumentListStamp('processing')).toBeNull()

    await loadCachedDocumentList('processing', async () => [{ id: 3 }], {
      force: true,
      stamp: 'later',
    })
    invalidateDocumentListCache('processing')
    expect(getDocumentListStamp('processing')).toBeNull()
  })
})
