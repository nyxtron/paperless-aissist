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
    t: (key: string, params?: { tag?: string; fields?: string }) =>
      params?.fields ? `${key} ${params.tag}: ${params.fields}` : key,
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

  describe('decisions in the preview', () => {
    const openPreview = async (data: Record<string, unknown>) => {
      Element.prototype.scrollIntoView = vi.fn()
      mocks.mockGetChatDocument.mockResolvedValue({ data: { id: 1, title: 'Invoice 2024' } })
      mocks.mockGetPreview.mockResolvedValue({
        data: { success: true, document_id: 1, steps: [], proposed_changes: {}, ...data },
      })
      render(<ChatPage />)
      fireEvent.click(await screen.findByText('Invoice 2024'))
      fireEvent.click(await screen.findByText('chat.preview'))
      await screen.findByText('chat.previewSuccess')
    }

    const review = (extra: Record<string, unknown> = {}) => ({
      tag: { id: 3, name: 'ai-review' },
      add_fields: [],
      remove: false,
      missing: false,
      ...extra,
    })

    it('notes how a field was decided and unfolds the full request', async () => {
      await openPreview({
        steps: [
          {
            name: 'correspondent',
            status: 'completed',
            duration_ms: 5,
            details: {
              decision: {
                method: 'ollama_letters',
                provider: 'ollama',
                model: 'qwen2.5:7b',
                outcome: 'applied',
                reason: null,
                choice: 'Telekom',
                probability: 0.99,
                threshold: 0.9,
                top: [],
                requests: 1,
                mass: 1,
                fallback_reason: null,
                fallback_detail: null,
                request: {
                  text_chars: 20,
                  text_sha256: 'a',
                  rendered: '[user] <document text, 20 chars>',
                  full: '[user] Rechnung der Telekom',
                },
              },
            },
          },
        ],
      })

      expect(screen.getByText('decision.note.decided')).toBeInTheDocument()
      expect(screen.queryByText('[user] Rechnung der Telekom')).not.toBeInTheDocument()

      fireEvent.click(screen.getByText('decision.note.showRequest'))

      expect(screen.getByText('[user] Rechnung der Telekom')).toBeInTheDocument()
    })

    it('opens no proposed changes box when nothing is proposed', async () => {
      // The review plan is always present once a decision step ran, even
      // when it has nothing to add or remove.
      await openPreview({ steps: [], proposed_changes: { review: review() } })

      expect(screen.queryByText('chat.proposedChanges')).not.toBeInTheDocument()
    })

    it('says which fields would get the review tag', async () => {
      await openPreview({
        proposed_changes: { review: review({ add_fields: ['correspondent', 'document_type'] }) },
      })

      expect(
        screen.getByText(
          'chat.reviewAdd ai-review: decision.field.correspondent, decision.field.document_type',
        ),
      ).toBeInTheDocument()
      expect(screen.queryByText('chat.reviewRemove')).not.toBeInTheDocument()
      expect(screen.queryByText('chat.reviewMissing')).not.toBeInTheDocument()
    })

    it('warns that the review tag does not exist', async () => {
      await openPreview({
        proposed_changes: {
          review: review({ tag: { id: null, name: 'ai-review' }, missing: true }),
        },
      })

      expect(screen.getByText('chat.reviewMissing')).toBeInTheDocument()
    })

    it('names the steps in the chosen language', async () => {
      await openPreview({ steps: [{ name: 'document_type', status: 'completed', duration_ms: 3 }] })

      expect(screen.getByText('processing.stepName.document_type')).toBeInTheDocument()
      expect(screen.getByText('processing.stepStatus.completed')).toBeInTheDocument()
    })

    it('shows a status it does not know as it comes', async () => {
      await openPreview({ steps: [{ name: 'title', status: 'retried', duration_ms: 3 }] })

      expect(screen.getByText('retried')).toBeInTheDocument()
    })

    it('names the custom fields it would fill', async () => {
      await openPreview({
        proposed_changes: {
          custom_fields: [
            { id: 3, name: 'Seiten', value: null },
            { id: 7, name: 'rechnungsbetrag', value: 'EUR104.99' },
          ],
        },
      })

      expect(
        screen.getByText('processing.updateCustomFields rechnungsbetrag: EUR104.99'),
      ).toBeInTheDocument()
      expect(screen.queryByText(/Seiten/)).not.toBeInTheDocument()
    })

    it('opens no proposed changes box for fields that stay empty', async () => {
      await openPreview({
        proposed_changes: {
          custom_fields: [
            { id: 3, name: 'Seiten', value: null },
            { id: 5, name: 'Links', value: [] },
          ],
        },
      })

      expect(screen.queryByText('chat.proposedChanges')).not.toBeInTheDocument()
    })

    it('says the review tag would come off', async () => {
      await openPreview({ proposed_changes: { review: review({ remove: true }) } })

      expect(screen.getByText('chat.reviewRemove')).toBeInTheDocument()
      expect(screen.queryByText(/chat\.reviewAdd/)).not.toBeInTheDocument()
    })
  })
})

