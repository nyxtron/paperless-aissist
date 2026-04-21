import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import ProcessingPanel from '../components/ProcessingPanel'

const mocks = vi.hoisted(() => ({
  mockGetTagged: vi.fn(),
  mockTrigger: vi.fn(),
  mockGetStatus: vi.fn(),
}))

vi.mock('../api/client', () => ({
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
})
