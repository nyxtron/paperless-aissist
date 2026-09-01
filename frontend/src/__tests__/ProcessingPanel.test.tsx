import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import ProcessingPanel, { clearProcessingDocumentCacheForTests } from '../components/ProcessingPanel'

const mocks = vi.hoisted(() => ({
  mockGetConfig: vi.fn(),
  mockGetTagged: vi.fn(),
  mockTrigger: vi.fn(),
  mockProcess: vi.fn(),
  mockGetStatus: vi.fn(),
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
