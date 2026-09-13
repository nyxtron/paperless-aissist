export type DocumentListCacheKey = 'chat' | 'processing'

interface CacheEntry<T> {
  data: T[] | null
  loadedAt: number | null
  // The server's last_finished_at the copy was taken under, see listIsBehindTheRun.
  stamp: string | null
  inFlight: Promise<T[]> | null
}

const DOCUMENT_LIST_CACHE_TTL_MS = 60 * 60 * 1000

const cache: Record<DocumentListCacheKey, CacheEntry<unknown>> = {
  chat: { data: null, loadedAt: null, stamp: null, inFlight: null },
  processing: { data: null, loadedAt: null, stamp: null, inFlight: null },
}

function isFresh(entry: CacheEntry<unknown>, now = Date.now()): boolean {
  return entry.data !== null
    && entry.loadedAt !== null
    && now - entry.loadedAt < DOCUMENT_LIST_CACHE_TTL_MS
}

export function getCachedDocumentList<T>(key: DocumentListCacheKey): T[] | null {
  const entry = cache[key]
  if (!isFresh(entry)) return null

  return entry.data as T[]
}

export async function loadCachedDocumentList<T>(
  key: DocumentListCacheKey,
  fetcher: () => Promise<T[]>,
  options: { force?: boolean; stamp?: string | null } = {},
): Promise<T[]> {
  const entry = cache[key] as CacheEntry<T>

  if (entry.inFlight) {
    return entry.inFlight
  }

  if (!options.force && isFresh(entry)) {
    return entry.data as T[]
  }

  entry.inFlight = fetcher()
    .then((data) => {
      entry.data = data
      entry.loadedAt = Date.now()
      entry.stamp = options.stamp ?? null
      return data
    })
    .finally(() => {
      entry.inFlight = null
    })

  return entry.inFlight
}

export function getDocumentListStamp(key: DocumentListCacheKey): string | null {
  return cache[key].stamp
}

export function invalidateDocumentListCache(key: DocumentListCacheKey): void {
  cache[key].data = null
  cache[key].loadedAt = null
  cache[key].stamp = null
}

export function setCachedDocumentList<T>(key: DocumentListCacheKey, data: T[]): void {
  cache[key].data = data
  cache[key].loadedAt = Date.now()
  cache[key].inFlight = null
}

export function clearDocumentListCache(): void {
  for (const key of Object.keys(cache) as DocumentListCacheKey[]) {
    cache[key].data = null
    cache[key].loadedAt = null
    cache[key].stamp = null
    cache[key].inFlight = null
  }
}

// A finished document changes the queue in Paperless. The list is cached so the
// page does not ask on every visit, which left it stale while the scheduler
// worked in the background (issue #53). The status carries the moment a
// document last finished; the copy remembers the value it was taken under.
// Comparing those two strings needs no clock, so a skewed server clock can
// neither loop reloads nor hide a finish, and a finish that lands while a
// request is on its way still shows up as a new value on the next poll.
export function listIsBehindTheRun(
  hasCopy: boolean,
  copyStamp: string | null,
  serverStamp: string | null | undefined,
): boolean {
  if (!hasCopy) return true
  return (serverStamp ?? null) !== copyStamp
}
