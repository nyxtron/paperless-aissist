import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { toast } from 'sonner'

import ConfigPanel, { SENSITIVE_KEYS } from '../components/ConfigPanel'

const mocks = vi.hoisted(() => ({
  mockGetAll: vi.fn(),
  mockSet: vi.fn(),
  mockDelete: vi.fn(),
  mockGetTags: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    getAll: mocks.mockGetAll,
    set: mocks.mockSet,
    delete: mocks.mockDelete,
    testConnection: vi.fn(),
  },
  documentsApi: {
    getTags: mocks.mockGetTags,
  },
  schedulerApi: {
    getStatus: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    clearState: vi.fn(),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

describe('ConfigPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.mockGetAll.mockResolvedValue({
      data: {
        data: {},
        secrets_set: [],
      },
    })
    mocks.mockSet.mockResolvedValue({ data: { key: 'document_list_refresh_mode', value: 'manual' } })
    mocks.mockGetTags.mockResolvedValue({ data: { tags: [] } })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // A stored decision key with an own provider; the delete empties the stored list.
  const storeDecisionKey = () => {
    let stored = ['llm_api_key_decision']
    mocks.mockGetAll.mockImplementation(async () => ({
      data: {
        data: {
          llm_provider_decision: 'openai',
          llm_api_base_decision: 'https://api.openai.com/v1',
        },
        secrets_set: stored,
      },
    }))
    mocks.mockDelete.mockImplementation(async () => {
      stored = []
      return { data: {} }
    })
  }

  const openDecisionKey = async () => {
    render(<ConfigPanel />)
    fireEvent.click(await screen.findByText('config.tabLLM'))
    await screen.findByText('config.decisionRemoveKey')
    return screen.getByLabelText('config.apiKey')
  }

  const savedKeys = () => mocks.mockSet.mock.calls.map(([key]) => key)

  it('does not store a removed decision key again on save', async () => {
    storeDecisionKey()
    const key = await openDecisionKey()

    fireEvent.change(key, { target: { value: 'sk-typed' } })
    expect(key).toHaveValue('sk-typed')
    fireEvent.click(screen.getByText('config.decisionRemoveKey'))

    await waitFor(() =>
      expect(screen.queryByText('config.decisionRemoveKey')).not.toBeInTheDocument(),
    )
    expect(mocks.mockDelete).toHaveBeenCalledWith('llm_api_key_decision')
    expect(key).toHaveValue('')

    fireEvent.click(screen.getByText('config.saveConfiguration'))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('config.savedSuccess'))
    expect(mocks.mockSet).toHaveBeenCalledWith('llm_provider_decision', 'openai')
    expect(savedKeys()).not.toContain('llm_api_key_decision')
  })

  it('drops a pending save of the decision key when it is removed', async () => {
    storeDecisionKey()
    const key = await openDecisionKey()

    vi.useFakeTimers()
    fireEvent.change(key, { target: { value: 'sk-typed' } })
    fireEvent.change(screen.getByLabelText('config.model'), { target: { value: 'gpt-4o' } })
    fireEvent.click(screen.getByText('config.decisionRemoveKey'))
    await act(() => vi.advanceTimersByTimeAsync(1500))

    expect(mocks.mockDelete).toHaveBeenCalledWith('llm_api_key_decision')
    expect(mocks.mockSet).toHaveBeenCalledWith('llm_model_decision', 'gpt-4o')
    expect(savedKeys()).not.toContain('llm_api_key_decision')
  })

  it('shows the stored threshold again when the save is refused', async () => {
    mocks.mockGetAll.mockResolvedValue({
      data: { data: { decision_threshold_correspondent: '0.95' }, secrets_set: [] },
    })
    render(<ConfigPanel />)
    fireEvent.click(await screen.findByText('config.tabLLM'))
    const [threshold] = await screen.findAllByLabelText('config.decisionThreshold')
    expect(threshold).toHaveValue(0.95)

    vi.useFakeTimers()
    mocks.mockSet.mockRejectedValue({ response: { status: 400 } })
    fireEvent.change(threshold, { target: { value: '' } })
    expect(threshold).toHaveValue(null)
    await act(() => vi.advanceTimersByTimeAsync(1500))

    expect(mocks.mockSet).toHaveBeenCalledWith('decision_threshold_correspondent', '')
    expect(toast.error).toHaveBeenCalledWith('config.saveKeyFailed')
    expect(threshold).toHaveValue(0.95)
  })

  it('treats the decision model key as a secret', () => {
    expect(SENSITIVE_KEYS.has('llm_api_key_decision')).toBe(true)
  })

  it('shows the decision mode section on the LLM tab', async () => {
    render(<ConfigPanel />)

    fireEvent.click(await screen.findByText('config.tabLLM'))

    expect(await screen.findByText('config.decisionSection')).toBeInTheDocument()
  })

  it('saves document list refresh mode immediately when changed', async () => {
    render(<ConfigPanel />)

    fireEvent.click(await screen.findByText('config.tabAdvanced'))
    fireEvent.change(screen.getByLabelText('config.documentListRefreshMode'), {
      target: { value: 'manual' },
    })

    await waitFor(() => {
      expect(mocks.mockSet).toHaveBeenCalledWith('document_list_refresh_mode', 'manual')
    })
  })

  it('renders and saves vision PDF input mode', async () => {
    render(<ConfigPanel />)

    fireEvent.click(await screen.findByText('config.tabLLM'))
    const pdfMode = await screen.findByLabelText('config.visionPdfMode')

    expect(pdfMode).toHaveValue('auto')
    expect(screen.getByText('config.visionPdfModeAuto')).toBeInTheDocument()

    fireEvent.change(pdfMode, { target: { value: 'page_images' } })
    fireEvent.click(screen.getByText('config.saveConfiguration'))

    await waitFor(() => {
      expect(mocks.mockSet).toHaveBeenCalledWith('vision_pdf_mode', 'page_images')
    })
  })

  it('renders and saves Ollama context window', async () => {
    render(<ConfigPanel />)

    fireEvent.click(await screen.findByText('config.tabLLM'))
    const contextWindow = await screen.findByLabelText('config.llmContextWindow')

    expect(contextWindow).toHaveValue(null)

    fireEvent.change(contextWindow, { target: { value: '16384' } })
    fireEvent.click(screen.getByText('config.saveConfiguration'))

    await waitFor(() => {
      expect(mocks.mockSet).toHaveBeenCalledWith('llm_num_ctx', '16384')
    })
  })

  it('renders and saves OCR fix max chars', async () => {
    render(<ConfigPanel />)

    fireEvent.click(await screen.findByText('config.tabAdvanced'))
    const maxChars = await screen.findByLabelText('config.ocrFixMaxChars')

    expect(maxChars).toHaveValue(10000)

    fireEvent.change(maxChars, { target: { value: '20000' } })
    fireEvent.click(screen.getByText('config.saveConfiguration'))

    await waitFor(() => {
      expect(mocks.mockSet).toHaveBeenCalledWith('ocr_fix_max_chars', '20000')
    })
  })
})
