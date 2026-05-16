import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import ProcessingPanel, { clearProcessingDocumentCacheForTests } from '../components/ProcessingPanel'

const mocks = vi.hoisted(() => ({
  mockGetConfig: vi.fn(),
  mockGetTagged: vi.fn(),
  mockTrigger: vi.fn(),
  mockGetStatus: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    get: mocks.mockGetConfig,
  },
  documentsApi: {
    getTagged: mocks.mockGetTagged,
    trigger: mocks.mockTrigger,
    process: vi.fn(),
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
        documents: [
          { id: 1, title: 'Invoice 2024', created: '2024-01-15', added: '2024-01-15', tags: [5] },
          { id: 2, title: 'Contract ABC', created: '2024-01-14', added: '2024-01-14', tags: [5] },
        ],
      },
    })
    mocks.mockTrigger.mockResolvedValue({ data: { processed: 2 } })
    mocks.mockGetStatus.mockResolvedValue({
      data: {
        running: true,
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

  it('force reloads the document list once after processing all documents', async () => {
    render(<ProcessingPanel />)

    await waitFor(() => {
      expect(screen.getByText('Invoice 2024')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText(/processing.processAll/i))

    await waitFor(() => {
      expect(mocks.mockTrigger).toHaveBeenCalledTimes(1)
      expect(mocks.mockGetTagged).toHaveBeenCalledTimes(2)
    })
  })
})
