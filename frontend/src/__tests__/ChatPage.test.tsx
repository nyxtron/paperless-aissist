import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import ChatPage, { clearChatDocumentCacheForTests } from '../pages/ChatPage'

const mocks = vi.hoisted(() => ({
  mockGetConfig: vi.fn(),
  mockGetChatList: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    get: mocks.mockGetConfig,
  },
  documentsApi: {
    getChatList: mocks.mockGetChatList,
    searchPaperless: vi.fn(),
    getChatDocument: vi.fn(),
    getPreview: vi.fn(),
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
})
