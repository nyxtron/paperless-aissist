import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import ChatPage, { clearChatDocumentCacheForTests } from '../pages/ChatPage'

const mocks = vi.hoisted(() => ({
  mockGetConfig: vi.fn(),
  mockGetChatList: vi.fn(),
  mockSearchPaperless: vi.fn(),
  mockGetChatDocument: vi.fn(),
  mockGetPreview: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    get: mocks.mockGetConfig,
  },
  documentsApi: {
    getChatList: mocks.mockGetChatList,
    searchPaperless: mocks.mockSearchPaperless,
    getChatDocument: mocks.mockGetChatDocument,
    getPreview: mocks.mockGetPreview,
    chat: vi.fn(),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('ChatPage', () => {
  beforeEach(() => {
    clearChatDocumentCacheForTests()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'automatic' } })
    mocks.mockGetChatList.mockResolvedValue({
      data: {
        documents: [{ id: 1, title: 'Invoice 2024', created: '2024-01-15' }],
      },
    })
    mocks.mockSearchPaperless.mockResolvedValue({
      data: {
        results: [],
      },
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('waits for manual refresh when document list refresh mode is manual', async () => {
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'manual' } })

    render(<ChatPage />)

    await waitFor(() => {
      expect(screen.getByText('chat.manualRefreshTitle')).toBeInTheDocument()
    })
    expect(mocks.mockGetChatList).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('common.refresh'))

    await waitFor(() => {
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
  })

  it('uses fresh cached documents on automatic remount without another list request', async () => {
    const firstRender = render(<ChatPage />)

    await waitFor(() => {
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    firstRender.unmount()
    render(<ChatPage />)

    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
  })

  it('reuses an in-flight automatic document list request', async () => {
    let resolveDocuments: (value: {
      data: {
        documents: Array<{ id: number; title: string; created: string }>
      }
    }) => void = () => undefined

    mocks.mockGetChatList.mockImplementation(
      () => new Promise((resolve) => {
        resolveDocuments = resolve
      }),
    )

    render(<ChatPage />)
    render(<ChatPage />)

    await waitFor(() => {
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
    })

    resolveDocuments({
      data: {
        documents: [{ id: 1, title: 'Invoice 2024', created: '2024-01-15' }],
      },
    })

    await waitFor(() => {
      expect(screen.getAllByText('Invoice 2024')).toHaveLength(2)
    })
  })

  it('forces a document list reload from the refresh button', async () => {
    render(<ChatPage />)

    await waitFor(() => {
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByText('common.refresh'))

    await waitFor(() => {
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(2)
    })
  })

  it('shows cached documents in manual mode without automatic reload', async () => {
    const firstRender = render(<ChatPage />)

    await waitFor(() => {
      expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    firstRender.unmount()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'manual' } })

    render(<ChatPage />)

    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    expect(screen.queryByText('chat.manualRefreshTitle')).not.toBeInTheDocument()
    expect(mocks.mockGetChatList).toHaveBeenCalledTimes(1)
  })

  it('renders more than five document search results', async () => {
    mocks.mockSearchPaperless.mockResolvedValue({
      data: {
        results: Array.from({ length: 7 }, (_, index) => ({
          id: index + 1,
          title: `Invoice ${index + 1}`,
          created: `2026-06-${String(index + 1).padStart(2, '0')}`,
        })),
      },
    })

    render(<ChatPage />)

    fireEvent.change(screen.getByPlaceholderText('chat.searchPlaceholder'), {
      target: { value: 'invoice' },
    })

    await waitFor(() => {
      expect(screen.getByText('Invoice 7')).toBeInTheDocument()
    })
    expect(screen.getAllByText(/Invoice \d/)).toHaveLength(7)
  })

  it('warns in the preview when a step saw only part of its prompt', async () => {
    // jsdom has no layout, so the chat's scroll-to-bottom needs a stand-in.
    Element.prototype.scrollIntoView = vi.fn()
    mocks.mockGetChatDocument.mockResolvedValue({ data: { id: 1, title: 'Invoice 2024' } })
    mocks.mockGetPreview.mockResolvedValue({
      data: {
        success: true,
        document_id: 1,
        steps: [
          {
            name: 'title',
            status: 'completed',
            duration_ms: 900,
            details: { prompt_cut: { evaluated: 2050, window: 4096 } },
          },
          { name: 'tags', status: 'completed', duration_ms: 300 },
        ],
        proposed_changes: {},
      },
    })
    render(<ChatPage />)

    fireEvent.click(await screen.findByText('Invoice 2024'))
    fireEvent.click(await screen.findByText('chat.preview'))

    expect(await screen.findAllByText('processing.promptCut')).toHaveLength(1)
  })
})

