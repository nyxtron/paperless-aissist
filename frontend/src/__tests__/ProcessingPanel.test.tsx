import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup, within } from '@testing-library/react'
import ProcessingPanel, { clearProcessingDocumentCacheForTests } from '../components/ProcessingPanel'
import { getDocumentListStamp, listIsBehindTheRun } from '../utils/documentListCache'

const mocks = vi.hoisted(() => ({
  mockGetConfig: vi.fn(),
  mockGetTagged: vi.fn(),
  mockTrigger: vi.fn(),
  mockProcess: vi.fn(),
  mockGetStatus: vi.fn(),
  mockStopRun: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    get: mocks.mockGetConfig,
  },
  documentsApi: {
    getTagged: mocks.mockGetTagged,
    trigger: mocks.mockTrigger,
    process: mocks.mockProcess,
  },
  schedulerApi: {
    getStatus: mocks.mockGetStatus,
    stopRun: mocks.mockStopRun,
    start: vi.fn(),
    stop: vi.fn(),
    update: vi.fn(),
    triggerNow: vi.fn(),
    clearState: vi.fn(),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: { tag?: string; fields?: string }) =>
      params?.fields ? `${key} ${params.tag}: ${params.fields}` : key,
    i18n: { language: 'en' },
  }),
}))

describe('ProcessingPanel', () => {
  beforeEach(() => {
    clearProcessingDocumentCacheForTests()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'automatic' } })
    mocks.mockGetTagged.mockResolvedValue({
      data: {
        paperless_url: 'http://paperless.test/',
        documents: [
          { id: 1, title: 'Invoice 2024', created: '2024-01-15', added: '2024-01-15', tags: [5] },
          { id: 2, title: 'Contract ABC', created: '2024-01-14', added: '2024-01-14', tags: [5] },
        ],
      },
    })
    mocks.mockTrigger.mockResolvedValue({
      data: {
        processed: 2,
        results: [
          { success: true, document_id: 1 },
          { success: true, document_id: 2 },
        ],
      },
    })
    mocks.mockProcess.mockResolvedValue({
      data: {
        success: true,
        document_id: 1,
        title: 'Invoice 2024',
        updates: {},
        processing_time_ms: 1200,
        steps: [
          {
            name: 'date',
            status: 'completed',
            duration_ms: 800,
            details: {
              created_date: '2026-04-28',
              confidence: 'high',
              evidence: 'Rechnungsdatum: Dienstag, 28. April 2026',
            },
          },
        ],
        proposed_changes: {},
      },
    })
    mocks.mockStopRun.mockResolvedValue({ data: { success: true, stopping: true } })
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        interval_minutes: 5,
        next_run: null,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
      },
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders section title', async () => {
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('processing.sectionTitle')).toBeInTheDocument()
    })
  })

  it('renders document list after loading', async () => {
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
      expect(screen.getByText('Contract ABC')).toBeInTheDocument()
    })
  })

  it('renders Paperless document links when the tagged response includes a URL', async () => {
    render(<ProcessingPanel />)

    const invoiceLink = await screen.findByRole('link', { name: /Invoice 2024/ })
    expect(invoiceLink).toHaveAttribute('href', 'http://paperless.test/documents/1')
    expect(invoiceLink).toHaveAttribute('target', '_blank')
    expect(invoiceLink).toHaveAttribute('rel', 'noreferrer')
    expect(invoiceLink).toHaveTextContent('#1')
  })

  it('renders scheduler running status', async () => {
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('processing.schedulerRunning')).toBeInTheDocument()
    })
  })

  it('renders process all button', async () => {
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText(/processing.processAll/i)).toBeInTheDocument()
    })
  })

  it('renders refresh button', async () => {
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('common.refresh')).toBeInTheDocument()
    })
  })

  it('waits for manual refresh when document list refresh mode is manual', async () => {
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'manual' } })

    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('processing.manualRefreshTitle')).toBeInTheDocument()
    })
    expect(mocks.mockGetTagged).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('common.refresh'))

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
  })

  it('uses fresh cached documents on automatic remount without another list request', async () => {
    const firstRender = render(<ProcessingPanel />)

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    firstRender.unmount()
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
  })

  it('reloads the list when a document finished after the copy was taken', async () => {
    const firstRender = render(<ProcessingPanel />)
    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
    })
    firstRender.unmount()

    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: '2026-09-12T10:00:00.422867+00:00',
      },
    })
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
    })
  })

  it('keeps the list on screen while the poll reloads it', async () => {
    const firstRender = render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    firstRender.unmount()

    let resolveReload: (value: { data: { documents: unknown[] } }) => void = () => {}
    mocks.mockGetTagged.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveReload = resolve
      }),
    )
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: '2026-09-12T10:00:00+00:00',
      },
    })
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
    })
    expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    expect(screen.queryByText('common.loading')).not.toBeInTheDocument()

    resolveReload({ data: { documents: [] } })
    await waitFor(() => {
      expect(screen.queryByText('Invoice 2024')).not.toBeInTheDocument()
    })
  })

  it('keeps the cached list while the last finish is the one the copy was taken under', async () => {
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: '2026-09-12T10:00:00+00:00',
      },
    })
    const firstRender = render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    firstRender.unmount()

    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
  })

  it('loads the list once when the status cannot be read', async () => {
    mocks.mockGetStatus.mockRejectedValue(new Error('down'))
    const firstRender = render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    firstRender.unmount()

    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
  })

  it('records the manual refresh under the stamp the server reports', async () => {
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
    })

    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: '2026-09-12T11:00:00+00:00',
      },
    })
    fireEvent.click(screen.getByText('common.refresh'))

    await waitFor(() => {
      expect(getDocumentListStamp('processing')).toBe('2026-09-12T11:00:00+00:00')
    })
    const asked = mocks.mockGetTagged.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(mocks.mockGetTagged).toHaveBeenCalledTimes(asked)
  })

  it('reloads while the page stays open and a document finishes', async () => {
    // The reported case: nobody navigates, the scheduler works in the background.
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    mocks.mockGetTagged.mockResolvedValue({
      data: { paperless_url: 'http://paperless.test/', documents: [] },
    })
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: '2026-09-13T10:00:00+00:00',
      },
    })

    // The next poll of the running interval brings the new stamp.
    await waitFor(
      () => {
        expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
      },
      { timeout: 4000 },
    )
    await waitFor(() => {
      expect(screen.queryByText('Invoice 2024')).not.toBeInTheDocument()
    })
  })

  it('keeps the list on screen when a poll-driven reload fails', async () => {
    const firstRender = render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })
    firstRender.unmount()

    mocks.mockGetTagged.mockRejectedValueOnce(new Error('backend gone'))
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: '2026-09-12T10:00:00+00:00',
      },
    })
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
    })
    expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    expect(screen.queryByText('backend gone')).not.toBeInTheDocument()
  })

  it('asks for the list once when a single document was processed', async () => {
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
    })

    // The document finishes, so the status that follows carries a new stamp.
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: '2026-09-12T10:00:00+00:00',
      },
    })
    fireEvent.click(screen.getAllByText('processing.processBtn')[0])

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
    })
    // Stored under the stamp that already covers this document, so the next
    // poll finds nothing to do instead of asking for the same list again.
    await waitFor(() => {
      expect(getDocumentListStamp('processing')).toBe('2026-09-12T10:00:00+00:00')
    })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
  })

  it('leaves the list alone in manual mode even when a document finished', async () => {
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'manual' } })
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_finished_at: new Date(Date.now() + 60_000).toISOString(),
      },
    })

    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('processing.manualRefreshTitle')).toBeInTheDocument()
    })
    expect(mocks.mockGetTagged).not.toHaveBeenCalled()
  })

  it('reuses an in-flight automatic document list request', async () => {
    let resolveDocuments: (value: {
      data: {
        documents: Array<{
          id: number
          title: string
          created: string
          added: string
          tags: number[]
        }>
      }
    }) => void = () => undefined

    mocks.mockGetTagged.mockImplementation(
      () => new Promise((resolve) => {
        resolveDocuments = resolve
      }),
    )

    render(<ProcessingPanel />)
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
    })

    resolveDocuments({
      data: {
        documents: [
          { id: 1, title: 'Invoice 2024', created: '2024-01-15', added: '2024-01-15', tags: [5] },
        ],
      },
    })

    await waitFor(() => {
      expect(screen.getAllByText('Invoice 2024')).toHaveLength(2)
    })
  })

  it('forces a document list reload from the refresh button', async () => {
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByText('common.refresh'))

    await waitFor(() => {
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
    })
  })

  it('does not reload the document list after processing all documents', async () => {
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText(/processing.processAll/i))

    await waitFor(() => {
      expect(mocks.mockTrigger).toHaveBeenCalledTimes(1)
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(1)
    })
  })

  it('removes successfully processed documents from the visible list', async () => {
    mocks.mockTrigger.mockResolvedValue({
      data: {
        processed: 1,
        results: [
          { success: true, document_id: 1 },
          { success: false, document_id: 2 },
        ],
      },
    })

    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
      expect(screen.getByText('Contract ABC')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText(/processing.processAll/i))

    await waitFor(() => {
      expect(screen.queryByText('Invoice 2024')).not.toBeInTheDocument()
      expect(screen.getByText('Contract ABC')).toBeInTheDocument()
    })
  })

  it('warns under a step whose prompt Ollama had to cut', async () => {
    mocks.mockProcess.mockResolvedValue({
      data: {
        success: true,
        document_id: 1,
        title: 'Invoice 2024',
        updates: {},
        processing_time_ms: 1200,
        steps: [
          {
            name: 'title',
            status: 'completed',
            duration_ms: 800,
            details: { prompt_cut: { evaluated: 2050, window: 4096 } },
          },
          { name: 'tags', status: 'completed', duration_ms: 300 },
        ],
        proposed_changes: {},
      },
    })
    render(<ProcessingPanel />)
    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByText(/processing.processBtn/i)[0])

    expect(await screen.findAllByText('processing.promptCut')).toHaveLength(1)
  })

  it('shows a decision note under a step', async () => {
    mocks.mockProcess.mockResolvedValue({
      data: {
        success: true,
        document_id: 1,
        title: 'Doc',
        updates: {},
        processing_time_ms: 1,
        proposed_changes: {},
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
                request: { text_chars: 1, text_sha256: 'a', rendered: 'r' },
              },
            },
          },
        ],
      },
    })
    render(<ProcessingPanel />)
    await screen.findByText('Invoice 2024')

    fireEvent.click(screen.getAllByText(/processing.processBtn/i)[0])

    expect(await screen.findByText('decision.note.decided')).toBeInTheDocument()
  })

  describe('review tag in the run result', () => {
    const review = (extra: Record<string, unknown> = {}) => ({
      tag: { id: 3, name: 'ai-review' },
      add_fields: [],
      remove: false,
      missing: false,
      ...extra,
    })

    const processWith = async (
      proposedChanges: Record<string, unknown>,
      extra: Record<string, unknown> = {},
    ) => {
      mocks.mockProcess.mockResolvedValue({
        data: {
          success: true,
          document_id: 1,
          title: 'Invoice 2024',
          updates: {},
          processing_time_ms: 1,
          steps: [{ name: 'correspondent', status: 'completed', duration_ms: 5 }],
          proposed_changes: proposedChanges,
          ...extra,
        },
      })
      render(<ProcessingPanel />)
      await screen.findByText('Invoice 2024')
      fireEvent.click(screen.getAllByText(/processing.processBtn/i)[0])
      await screen.findByText('processing.resultTitle')
    }

    it('names the fields the review tag was added for', async () => {
      await processWith({ review: review({ add_fields: ['correspondent', 'document_type'] }) })

      expect(screen.getByText('processing.updatesApplied')).toBeInTheDocument()
      expect(
        screen.getByText(
          'processing.reviewTagAdded ai-review: decision.field.correspondent, decision.field.document_type',
        ),
      ).toBeInTheDocument()
    })

    it('says what to do about the review tag', async () => {
      await processWith({ review: review({ add_fields: ['document_type'] }) })

      expect(screen.getByText('processing.reviewTagHint')).toBeInTheDocument()
    })

    it('lists applied fields and tags as text and names the steps', async () => {
      await processWith({
        tags: [
          { id: 1, name: 'Oliver' },
          { id: 2, name: 'eMail' },
        ],
        custom_fields: [
          { id: 3, name: 'Seiten', value: null },
          { id: 7, name: 'rechnungsbetrag', value: 'EUR167.40' },
        ],
      })

      expect(screen.getByText('processing.updateTags Oliver, eMail')).toBeInTheDocument()
      expect(
        screen.getByText('processing.updateCustomFields rechnungsbetrag: EUR167.40'),
      ).toBeInTheDocument()
      expect(screen.queryByText(/Seiten/)).not.toBeInTheDocument()
      expect(screen.getByText('processing.stepName.correspondent')).toBeInTheDocument()
    })

    it('writes yes or no for a checkbox field and sets fields apart', async () => {
      await processWith({
        custom_fields: [
          { id: 4, name: 'Bezahlt', value: false },
          { id: 5, name: 'Bezug', value: [12, 34] },
          { id: 7, name: 'rechnungsbetrag', value: 'EUR167.40' },
        ],
      })

      expect(
        screen.getByText(
          'processing.updateCustomFields Bezahlt: common.no · Bezug: 12, 34 · rechnungsbetrag: EUR167.40',
        ),
      ).toBeInTheDocument()
    })

    it('shows the date the date step found', async () => {
      await processWith({ created_date: '2026-03-01' })

      expect(screen.getByText('processing.updatesApplied')).toBeInTheDocument()
      expect(screen.getByText('processing.updateDate 2026-03-01')).toBeInTheDocument()
    })

    it('opens no updates box for changes it would not show', async () => {
      await processWith({ text: 'recognised text', tags: [] })

      expect(screen.queryByText('processing.updatesApplied')).not.toBeInTheDocument()
    })

    it('opens no updates box for custom fields that stay empty', async () => {
      await processWith({ custom_fields: [{ id: 3, name: 'Seiten', value: null }] })

      expect(screen.queryByText('processing.updatesApplied')).not.toBeInTheDocument()
    })

    it('says when the review tag came off', async () => {
      await processWith({ review: review({ remove: true }) })

      expect(screen.getByText('processing.reviewTagRemoved')).toBeInTheDocument()
      expect(screen.queryByText(/processing\.reviewTagAdded/)).not.toBeInTheDocument()
    })

    it('shows no empty updates box when the review tag stayed as it was', async () => {
      await processWith({ review: review() })

      expect(screen.queryByText('processing.updatesApplied')).not.toBeInTheDocument()
    })

    it('never claims a missing review tag was added', async () => {
      // The tag went between the check before the steps and the write, so
      // the document was left as it was.
      await processWith(
        {
          title: 'Invoice 2024',
          review: review({
            tag: { id: null, name: 'ai-review' },
            add_fields: ['correspondent'],
            missing: true,
          }),
        },
        { success: false, error: "Review tag 'ai-review' does not exist in Paperless" },
      )

      expect(screen.getByText('processing.updatesApplied')).toBeInTheDocument()
      expect(screen.queryByText(/processing\.reviewTagAdded/)).not.toBeInTheDocument()
    })
  })

  it('renders date step details in single document processing results', async () => {
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByText(/processing.processBtn/i)[0])

    expect(await screen.findByText(/created_date: 2026-04-28/)).toBeInTheDocument()
    expect(screen.getByText(/confidence: high/)).toBeInTheDocument()
    expect(screen.getByText(/Rechnungsdatum: Dienstag, 28. April 2026/)).toBeInTheDocument()
  })
})

describe('ProcessingPanel stopped-run notice', () => {
  beforeEach(() => {
    clearProcessingDocumentCacheForTests()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'automatic' } })
    mocks.mockGetTagged.mockResolvedValue({
      data: { paperless_url: 'http://paperless.test/', documents: [] },
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('explains why a run gave up early', async () => {
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        interval_minutes: 5,
        next_run: null,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_stop: {
          reason: 'Ollama request failed: All connection attempts failed',
          failures: 3,
          at: '2026-09-01T08:24:49+00:00',
        },
      },
    })

    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('processing.runStoppedTitle')).toBeInTheDocument()
    })
  })

  it('says nothing when no run was stopped', async () => {
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        interval_minutes: 5,
        next_run: null,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
        last_stop: null,
      },
    })

    render(<ProcessingPanel />)

    await waitFor(() => expect(mocks.mockGetStatus).toHaveBeenCalled())
    expect(screen.queryByText('processing.runStoppedTitle')).not.toBeInTheDocument()
  })
})

describe('ProcessingPanel trigger tags', () => {
  beforeEach(() => {
    clearProcessingDocumentCacheForTests()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'automatic' } })
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        interval_minutes: 5,
        next_run: null,
        is_processing: false,
        current_document_ids: [],
        active_documents: [],
      },
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('names the tags a queued document is waiting on', async () => {
    mocks.mockGetTagged.mockResolvedValue({
      data: {
        paperless_url: 'http://paperless.test/',
        documents: [
          {
            id: 1,
            title: 'Invoice',
            created: '2024-01-15',
            added: '2024-01-15',
            tags: [5, 6],
            tag_names: ['ai-ocr', 'ai-title'],
          },
        ],
      },
    })

    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('ai-ocr')).toBeInTheDocument()
    })
    expect(screen.getByText('ai-title')).toBeInTheDocument()
  })

  it('copes with a document the backend sent no names for', async () => {
    mocks.mockGetTagged.mockResolvedValue({
      data: {
        paperless_url: 'http://paperless.test/',
        documents: [
          { id: 1, title: 'Invoice', created: '2024-01-15', added: '2024-01-15', tags: [5] },
        ],
      },
    })

    render(<ProcessingPanel />)

    await waitFor(() => expect(screen.getByText('Invoice')).toBeInTheDocument())
  })

  it('names the tags of the document being processed', async () => {
    mocks.mockGetTagged.mockResolvedValue({
      data: { paperless_url: 'http://paperless.test/', documents: [] },
    })
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
        interval_minutes: 5,
        next_run: null,
        is_processing: true,
        current_document_ids: [42],
        active_documents: [{ document_id: 42, trigger_tags: ['ai-fields'] }],
      },
    })

    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('ai-fields')).toBeInTheDocument()
    })
  })
})

describe('listIsBehindTheRun', () => {
  it('wants a request when there is no copy', () => {
    expect(listIsBehindTheRun(false, null, null)).toBe(true)
    expect(listIsBehindTheRun(false, null, '2026-09-12T10:00:00+00:00')).toBe(true)
  })

  it('is content while the copy was taken under the current stamp', () => {
    expect(listIsBehindTheRun(true, null, null)).toBe(false)
    expect(listIsBehindTheRun(true, null, undefined)).toBe(false)
    expect(listIsBehindTheRun(true, 'a', 'a')).toBe(false)
  })

  it('is behind once the server reports a finish the copy was not taken under', () => {
    expect(listIsBehindTheRun(true, null, 'a')).toBe(true)
    expect(listIsBehindTheRun(true, 'a', 'b')).toBe(true)
    // Any change counts, whichever way the server clock moved.
    expect(listIsBehindTheRun(true, 'b', 'a')).toBe(true)
    expect(listIsBehindTheRun(true, 'a', null)).toBe(true)
  })
})

describe('ProcessingPanel while a run is going', () => {
  const running = (extra: Record<string, unknown> = {}) => ({
    data: {
      running: true,
      interval_minutes: 5,
      next_run: null,
      is_processing: true,
      current_document_ids: [1014],
      active_documents: [
        { document_id: 1014, trigger_tags: ['ai-ocr'], active_step: 'ocr' },
      ],
      ...extra,
    },
  })

  const idle = (extra: Record<string, unknown> = {}) => ({
    data: {
      running: true,
      interval_minutes: 5,
      next_run: null,
      is_processing: false,
      current_document_ids: [],
      active_documents: [],
      ...extra,
    },
  })

  beforeEach(() => {
    clearProcessingDocumentCacheForTests()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'automatic' } })
    mocks.mockGetTagged.mockResolvedValue({
      data: { paperless_url: 'http://paperless.test/', documents: [] },
    })
    mocks.mockStopRun.mockResolvedValue({ data: { success: true, stopping: true } })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('offers to stop the run and asks the backend once', async () => {
    mocks.mockGetStatus.mockResolvedValue(running())
    // The request is what makes the run say it is stopping.
    mocks.mockStopRun.mockImplementation(async () => {
      mocks.mockGetStatus.mockResolvedValue(running({ stop_requested: true }))
      return { data: { success: true, stopping: true } }
    })
    render(<ProcessingPanel />)

    fireEvent.click(await screen.findByText('processing.stopRun'))

    await waitFor(() => {
      expect(mocks.mockStopRun).toHaveBeenCalledTimes(1)
    })
    expect(await screen.findByText('processing.stopping')).toBeInTheDocument()
  })

  it('lets the next run be stopped as well', async () => {
    // The run that was stopped ends, the scheduler starts the next one, and the
    // button has to work again without reloading the page.
    mocks.mockGetStatus.mockResolvedValue(running())
    mocks.mockStopRun.mockImplementation(async () => {
      mocks.mockGetStatus.mockResolvedValue(running({ stop_requested: true }))
      return { data: { success: true, stopping: true } }
    })
    render(<ProcessingPanel />)

    fireEvent.click(await screen.findByText('processing.stopRun'))
    await screen.findByText('processing.stopping')

    mocks.mockGetStatus.mockResolvedValue(idle())
    await waitFor(
      () => {
        expect(screen.queryByText('processing.stopping')).not.toBeInTheDocument()
      },
      { timeout: 4000 },
    )

    mocks.mockGetStatus.mockResolvedValue(running())
    const again = await screen.findByText('processing.stopRun', undefined, { timeout: 4000 })

    expect(again).toBeEnabled()
  })

  it('asks once however often the button is pressed', async () => {
    mocks.mockGetStatus.mockResolvedValue(running())
    let release: (value: { data: unknown }) => void = () => {}
    mocks.mockStopRun.mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }),
    )
    render(<ProcessingPanel />)

    const button = await screen.findByText('processing.stopRun')
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)

    await waitFor(() => {
      expect(mocks.mockStopRun).toHaveBeenCalledTimes(1)
    })
    release({ data: { success: true, stopping: true } })
  })

  it('does not latch when there was no run to stop', async () => {
    mocks.mockGetStatus.mockResolvedValue(running())
    mocks.mockStopRun.mockResolvedValue({ data: { success: true, stopping: false } })
    render(<ProcessingPanel />)

    fireEvent.click(await screen.findByText('processing.stopRun'))

    await waitFor(() => {
      expect(mocks.mockStopRun).toHaveBeenCalledTimes(1)
    })
    expect(await screen.findByText('processing.stopRun')).toBeEnabled()
  })

  it('keeps the button usable when the request fails', async () => {
    mocks.mockGetStatus.mockResolvedValue(running())
    mocks.mockStopRun.mockRejectedValue(new Error('backend gone'))
    render(<ProcessingPanel />)

    fireEvent.click(await screen.findByText('processing.stopRun'))

    await waitFor(() => {
      expect(mocks.mockStopRun).toHaveBeenCalledTimes(1)
    })
    expect(await screen.findByText('processing.stopRun')).toBeEnabled()
  })

  it('keeps saying stopping while the run winds down', async () => {
    mocks.mockGetStatus.mockResolvedValue(running({ stop_requested: true }))
    render(<ProcessingPanel />)

    expect(await screen.findByText('processing.stopping')).toBeInTheDocument()
    expect(screen.getByText('processing.stopRequested')).toBeInTheDocument()
    expect(screen.queryByText('processing.stopRun')).not.toBeInTheDocument()
  })

  it('has nothing to stop when no run is going', async () => {
    mocks.mockGetStatus.mockResolvedValue(idle())
    render(<ProcessingPanel />)

    await screen.findByText('processing.schedulerRunning')
    expect(screen.queryByText('processing.stopRun')).not.toBeInTheDocument()
  })

  it('names the page a long document is on', async () => {
    mocks.mockGetStatus.mockResolvedValue(
      running({
        active_documents: [
          {
            document_id: 1014,
            trigger_tags: ['ai-ocr'],
            active_step: 'ocr',
            page: 3,
            pages: 12,
          },
        ],
      }),
    )
    render(<ProcessingPanel />)

    expect(await screen.findByText('processing.pageOfPages')).toBeInTheDocument()
  })

  it('keeps the page with the document it belongs to', async () => {
    // Three documents run at once by default, so a page label at the end of the
    // line would read as belonging to whichever document came last.
    mocks.mockGetStatus.mockResolvedValue(
      running({
        paperless_url: 'http://paperless.test/',
        current_document_ids: [1014, 1015],
        active_documents: [
          {
            document_id: 1014,
            trigger_tags: ['ai-ocr'],
            active_step: 'ocr',
            page: 7,
            pages: 9,
          },
          { document_id: 1015, trigger_tags: ['ai-title'], active_step: 'title' },
        ],
      }),
    )
    const { container } = render(<ProcessingPanel />)

    await screen.findByText('processing.pageOfPages')
    const reading = container.querySelector('a[href$="/documents/1014"]')!.closest('span')!
    const done = container.querySelector('a[href$="/documents/1015"]')!.closest('span')!

    expect(within(reading).getByText('processing.pageOfPages')).toBeInTheDocument()
    expect(within(done).queryByText('processing.pageOfPages')).not.toBeInTheDocument()
  })

  it('says nothing about pages for a document that is not being read', async () => {
    mocks.mockGetStatus.mockResolvedValue(running())
    render(<ProcessingPanel />)

    await screen.findByText('processing.stopRun')
    expect(screen.queryByText('processing.pageOfPages')).not.toBeInTheDocument()
  })

  it('tells a run stopped on request from one the failures ended', async () => {
    mocks.mockGetStatus.mockResolvedValue(
      idle({
        last_stop: {
          reason: 'stopped on request',
          failures: 0,
          at: '2026-09-13T10:00:00+00:00',
        },
      }),
    )
    render(<ProcessingPanel />)

    expect(await screen.findByText('processing.runStoppedByHand')).toBeInTheDocument()
    expect(screen.queryByText('processing.runStoppedBody')).not.toBeInTheDocument()
  })

  it('words a run stopped by a missing review tag', async () => {
    mocks.mockGetStatus.mockResolvedValue(
      idle({
        last_stop: {
          reason: "Review tag 'ai-review' does not exist in Paperless",
          failures: 0,
          at: '2026-10-01T10:00:00Z',
          kind: 'review_tag',
        },
      }),
    )
    render(<ProcessingPanel />)

    expect(await screen.findByText('processing.runStoppedReviewTag')).toBeInTheDocument()
    expect(screen.queryByText('processing.runStoppedByHand')).not.toBeInTheDocument()
  })

  it('still explains a run the failure limit cut off', async () => {
    mocks.mockGetStatus.mockResolvedValue(
      idle({
        last_stop: {
          reason: 'provider unavailable',
          failures: 3,
          at: '2026-09-13T10:00:00+00:00',
        },
      }),
    )
    render(<ProcessingPanel />)

    expect(await screen.findByText('processing.runStoppedBody')).toBeInTheDocument()
    expect(screen.queryByText('processing.runStoppedByHand')).not.toBeInTheDocument()
  })
})

