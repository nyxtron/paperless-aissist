export type DocumentListCacheKey = 'chat' | 'processing'

interface CacheEntry<T> {
  data: T[] | null
  loadedAt: number | null
  inFlight: Promise<T[]> | null
}

const DOCUMENT_LIST_CACHE_TTL_MS = 60 * 60 * 1000

const cache: Record<DocumentListCacheKey, CacheEntry<unknown>> = {
  chat: { data: null, loadedAt: null, inFlight: null },
  processing: { data: null, loadedAt: null, inFlight: null },
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
  options: { force?: boolean } = {},
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
      return data
    })
    .finally(() => {
      entry.inFlight = null
    })

  return entry.inFlight
}

export function invalidateDocumentListCache(key: DocumentListCacheKey): void {
  cache[key].data = null
  cache[key].loadedAt = null
}

export function clearDocumentListCache(): void {
  for (const key of Object.keys(cache) as DocumentListCacheKey[]) {
    cache[key].data = null
    cache[key].loadedAt = null
    cache[key].inFlight = null
  }
}
