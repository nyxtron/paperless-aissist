import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import type { CSSProperties, ReactNode } from 'react'

import Dashboard from '../components/Dashboard'
import { ThemeProvider } from '../contexts/ThemeContext'

const mocks = vi.hoisted(() => ({
  mockGetStats: vi.fn(),
  mockGetDaily: vi.fn(),
  mockGetRecent: vi.fn(),
  mockGetConfig: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    get: mocks.mockGetConfig,
  },
  statsApi: {
    get: mocks.mockGetStats,
    getDaily: mocks.mockGetDaily,
    getRecent: mocks.mockGetRecent,
    reset: vi.fn(),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: { id?: number }) => (
      params?.id ? `${key} ${params.id}` : key
    ),
  }),
}))

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div className="recharts-wrapper">{children}</div>
  ),
  PieChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Cell: () => <div />,
  BarChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: ({ tick }: { tick?: { fill?: string } }) => <div data-fill={tick?.fill} />,
  YAxis: ({ tick }: { tick?: { fill?: string } }) => <div data-fill={tick?.fill} />,
  Tooltip: ({ contentStyle }: { contentStyle?: CSSProperties }) => (
    <div style={contentStyle} />
  ),
}))

describe('Dashboard', () => {
  beforeEach(() => {
    mocks.mockGetStats.mockResolvedValue({
      data: {
        total_processed: 1,
        success: 1,
        failed: 0,
        skipped: 0,
        success_rate: 100,
        avg_processing_time_ms: 1200,
      },
    })
    mocks.mockGetDaily.mockResolvedValue({ data: [] })
    mocks.mockGetRecent.mockResolvedValue({
      data: [
        {
          id: 9,
          document_id: 42,
          document_title: 'Recent Invoice',
          status: 'success',
          llm_provider: null,
          llm_model: 'qwen3',
          llm_response: JSON.stringify({
            steps: [
              {
                name: 'date',
                details: {
                  created_date: '2026-04-28',
                  confidence: 'high',
                  evidence: 'Rechnungsdatum: Dienstag, 28. April 2026',
                },
              },
            ],
          }),
          error_message: null,
          processing_time_ms: 1200,
          processed_at: '2026-05-16T10:00:00Z',
        },
      ],
    })
    mocks.mockGetConfig.mockResolvedValue({ data: { value: 'http://paperless.test/' } })
  })

  it('renders recent processing log document links with visible IDs', async () => {
    render(<Dashboard />)

    const link = await screen.findByRole('link', { name: /Recent Invoice/ })
    expect(link).toHaveAttribute('href', 'http://paperless.test/documents/42')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')
    expect(screen.getByText('#42')).toBeInTheDocument()
    expect(await screen.findByText(/created_date: 2026-04-28/)).toBeInTheDocument()
    expect(screen.getByText(/confidence: high/)).toBeInTheDocument()
  })

  it('draws chart text in a light colour on the dark theme', async () => {
    vi.mocked(localStorage.getItem).mockReturnValue('dark')
    const { container } = render(<ThemeProvider><Dashboard /></ThemeProvider>)

    await waitFor(() => expect(container.querySelector('.recharts-wrapper')).toBeTruthy())
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(container.innerHTML).toContain('#9ca3af')
  })

  it('leaves chart colours untouched in light mode', async () => {
    vi.mocked(localStorage.getItem).mockReturnValue(null)
    const { container } = render(<ThemeProvider><Dashboard /></ThemeProvider>)

    await waitFor(() => expect(container.querySelector('.recharts-wrapper')).toBeTruthy())
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(container.innerHTML).not.toContain('#9ca3af')
    expect(container.innerHTML).not.toContain('#6b7280')
  })
})

describe('Dashboard trigger tags', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.mockGetConfig.mockResolvedValue({ data: { value: '' } })
    mocks.mockGetStats.mockResolvedValue({
      data: { total: 1, success: 1, failed: 0, skipped: 0 },
    })
    mocks.mockGetDaily.mockResolvedValue({ data: [] })
  })

  it('names the tags a run was triggered by', async () => {
    mocks.mockGetRecent.mockResolvedValue({
      data: [
        {
          id: 1,
          document_id: 42,
          document_title: 'Invoice',
          status: 'success',
          llm_provider: null,
          llm_model: null,
          llm_response: null,
          error_message: null,
          trigger_tags: 'ai-ocr, ai-title',
          processing_time_ms: 100,
          processed_at: '2026-09-01T10:00:00Z',
        },
      ],
    })

    render(<Dashboard />)

    expect(await screen.findByText('ai-ocr')).toBeInTheDocument()
    expect(screen.getByText('ai-title')).toBeInTheDocument()
  })

  it('stays quiet for entries written before the column existed', async () => {
    mocks.mockGetRecent.mockResolvedValue({
      data: [
        {
          id: 1,
          document_id: 42,
          document_title: 'Older Invoice',
          status: 'success',
          llm_provider: null,
          llm_model: null,
          llm_response: null,
          error_message: null,
          trigger_tags: null,
          processing_time_ms: 100,
          processed_at: '2026-09-01T10:00:00Z',
        },
      ],
    })

    render(<Dashboard />)

    expect(await screen.findByText('Older Invoice')).toBeInTheDocument()
  })
})
