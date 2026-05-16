import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'

import ProcessingPanel from '../components/ProcessingPanel'
import ChatPage from '../pages/ChatPage'
import { clearDocumentListCache } from '../utils/documentListCache'

const mocks = vi.hoisted(() => ({
  mockGetConfig: vi.fn(),
  mockGetTagged: vi.fn(),
  mockGetChatList: vi.fn(),
  mockGetStatus: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    get: mocks.mockGetConfig,
  },
  documentsApi: {
    getTagged: mocks.mockGetTagged,
    getChatList: mocks.mockGetChatList,
    trigger: vi.fn(),
    process: vi.fn(),
    searchPaperless: vi.fn(),
    getChatDocument: vi.fn(),
    getPreview: vi.fn(),
    chat: vi.fn(),
  },
  schedulerApi: {
    getStatus: mocks.mockGetStatus,
    start: vi.fn(),
    stop: vi.fn(),
    update: vi.fn(),
    triggerNow: vi.fn(),
    clearState: vi.fn(),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason?: unknown) => void = () => undefined
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })

  return { promise, resolve, reject }
}

describe('document list navigation smoke', () => {
  beforeEach(() => {
    clearDocumentListCache()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'automatic' } })
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: false,
        interval_minutes: 5,
        next_run: null,
        is_processing: false,
        current_doc_id: null,
      },
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    clearDocumentListCache()
  })

  it('dedupes in-flight Process and Chat list requests during rapid navigation', async () => {
    const processingRequest = deferred<{
      data: {
        documents: Array<{
          id: number
          title: string
          created: string
          added: string
          tags: number[]
        }>
      }
    }>()
    const chatRequest = deferred<{
      data: {
        documents: Array<{ id: number; title: string; created: string }>
      }
    }>()

    mocks.mockGetTagged.mockReturnValue(processingRequest.promise)
    mocks.mockGetChatList.mockReturnValue(chatRequest.promise)

    const processingFirst = render(<ProcessingPanel />)
    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
    })
    processingFirst.unmount()

    const chatFirst = render(<ChatPage />)
    await waitFor(() => {
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
    })
    chatFirst.unmount()

    const processingSecond = render(<ProcessingPanel />)
    const chatSecond = render(<ChatPage />)

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
    })

    processingRequest.resolve({
      data: {
        documents: [
          {
            id: 1,
            title: 'Processing Invoice',
            created: '2026-05-16',
            added: '2026-05-16',
            tags: [11],
          },
        ],
      },
    })
    chatRequest.resolve({
      data: {
        documents: [{ id: 2, title: 'Chat Invoice', created: '2026-05-16' }],
      },
    })

    await waitFor(() => {
      expect(screen.getByText('Processing Invoice')).toBeInTheDocument()
      expect(screen.getByText('Chat Invoice')).toBeInTheDocument()
    })

    processingSecond.unmount()
    chatSecond.unmount()
  })
})
