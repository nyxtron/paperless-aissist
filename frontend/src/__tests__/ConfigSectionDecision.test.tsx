import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ConfigSectionDecision } from '../components/ConfigSectionDecision'

const mocks = vi.hoisted(() => ({ getTags: vi.fn(), testDecision: vi.fn(), del: vi.fn() }))
vi.mock('../api/client', () => ({
  configApi: { testDecision: mocks.testDecision, delete: mocks.del },
  documentsApi: { getTags: mocks.getTags },
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params
        ? `${key} ${Object.entries(params)
            .map(([k, v]) => `${k}=${v}`)
            .join(' ')}`
        : key,
  }),
}))

const base = {
  llm_provider: 'ollama',
  llm_model: 'qwen2.5:7b',
  llm_api_base: 'http://main:11434',
}
const own = { ...base, llm_provider_decision: 'openai' }

describe('ConfigSectionDecision', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getTags.mockResolvedValue({ data: { tags: [{ id: 1, name: 'ai-review' }] } })
  })

  it('saves each toggle', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<ConfigSectionDecision config={base} onSave={onSave} secretsSet={[]} />)
    fireEvent.click(screen.getByLabelText('config.decisionCorrespondent'))
    expect(onSave).toHaveBeenCalledWith('decision_correspondent', 'true')
    fireEvent.click(screen.getByLabelText('config.decisionDocumentType'))
    expect(onSave).toHaveBeenCalledWith('decision_document_type', 'true')
  })

  it.each([
    [
      'config.decisionThreshold field=decision.field.correspondent',
      'decision_threshold_correspondent',
      '0.8',
    ],
    [
      'config.decisionThreshold field=decision.field.document_type',
      'decision_threshold_document_type',
      '0.75',
    ],
    [
      'config.decisionQuestion field=decision.field.correspondent',
      'decision_question_correspondent',
      'Wer schreibt?',
    ],
    [
      'config.decisionQuestion field=decision.field.document_type',
      'decision_question_document_type',
      'Welcher Typ?',
    ],
    ['config.decisionFormat', 'decision_format', 'nimble'],
    ['config.reviewTag', 'review_tag', 'needs-check'],
    ['config.provider', 'llm_provider_decision', 'openai'],
    ['config.model', 'llm_model_decision', 'nimble'],
    ['config.llmTimeout', 'llm_timeout_decision', '120'],
    ['config.decisionContextWindow', 'llm_num_ctx_decision', '8192'],
  ])('saves %s as %s', (label, key, value) => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<ConfigSectionDecision config={base} onSave={onSave} secretsSet={[]} />)
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
    expect(onSave).toHaveBeenCalledWith(key, value)
  })

  it.each([
    ['config.apiBaseUrl', 'llm_api_base_decision', 'http://decider:11434'],
    ['config.apiKey', 'llm_api_key_decision', 'sk-decide'],
  ])('saves %s as %s with an own provider', (label, key, value) => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<ConfigSectionDecision config={own} onSave={onSave} secretsSet={[]} />)
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
    expect(onSave).toHaveBeenCalledWith(key, value)
  })

  it('shows the default threshold as a placeholder, not as a value', () => {
    render(
      <ConfigSectionDecision
        config={{ ...base, decision_threshold_correspondent: '' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    const field = screen.getByLabelText(
      'config.decisionThreshold field=decision.field.correspondent',
    )
    expect(field).toHaveValue(null)
    expect(field).toHaveAttribute('placeholder', '0.9')
  })

  it('shows inherited placeholders and disables URL and key while the provider is empty', () => {
    const { rerender } = render(
      <ConfigSectionDecision
        config={base}
        onSave={vi.fn()}
        secretsSet={['llm_api_key_decision']}
      />,
    )
    expect(screen.getByPlaceholderText('qwen2.5:7b')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('http://main:11434')).toBeDisabled()
    expect(screen.getByLabelText('config.apiKey')).toBeDisabled()
    // a stored decision key is ignored while inherited
    expect(screen.getByLabelText('config.apiKey')).toHaveAttribute('placeholder', '')
    expect(screen.getByText('config.decisionInherited')).toBeInTheDocument()

    rerender(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={['llm_api_key']} />)
    expect(screen.getByLabelText('config.apiKey')).toHaveAttribute(
      'placeholder',
      'config.alreadySetPlaceholder',
    )
  })

  it('shows the URL the main connection falls back to while inherited', () => {
    // Only OpenRouter has a default URL; Ollama with no stored URL shows none.
    const { rerender } = render(
      <ConfigSectionDecision
        config={{ ...base, llm_provider: 'openrouter', llm_api_base: '' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(screen.getByLabelText('config.apiBaseUrl')).toBeDisabled()
    expect(screen.getByLabelText('config.apiBaseUrl')).toHaveAttribute(
      'placeholder',
      'https://openrouter.ai/api/v1',
    )

    rerender(
      <ConfigSectionDecision
        config={{ ...base, llm_api_base: '' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(screen.getByLabelText('config.apiBaseUrl')).toHaveAttribute('placeholder', '')
  })

  it('asks for a URL once an own provider is set', () => {
    render(<ConfigSectionDecision config={own} onSave={vi.fn()} secretsSet={['llm_api_key']} />)
    expect(screen.getByLabelText('config.apiBaseUrl')).not.toBeDisabled()
    expect(screen.getByText('config.decisionUrlRequired')).toBeInTheDocument()
    expect(screen.getByText('config.decisionModelRequired')).toBeInTheDocument()
    expect(screen.getByText('config.decisionModelHint')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('http://main:11434')).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('qwen2.5:7b')).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText('https://api.openai.com/v1')).toBeInTheDocument()
    // the main key is not used with an own provider
    expect(screen.getByLabelText('config.apiKey')).toHaveAttribute('placeholder', '')
  })

  it('needs no URL for OpenRouter', () => {
    render(
      <ConfigSectionDecision
        config={{ ...base, llm_provider_decision: 'openrouter', llm_model_decision: 'x/y' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(screen.queryByText('config.decisionUrlRequired')).not.toBeInTheDocument()
    expect(screen.queryByText('config.decisionModelRequired')).not.toBeInTheDocument()
  })

  it('warns when the chosen format cannot run on the provider', () => {
    const { rerender } = render(
      <ConfigSectionDecision
        config={{ ...own, llm_api_base_decision: 'http://x', decision_format: 'nimble' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(screen.getByText('config.decisionFormatUnusable')).toBeInTheDocument()

    rerender(
      <ConfigSectionDecision
        config={{ ...base, decision_format: 'nimble' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(screen.queryByText('config.decisionFormatUnusable')).not.toBeInTheDocument()

    rerender(
      <ConfigSectionDecision
        config={{ ...base, llm_provider: 'grok' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(screen.getByText('config.decisionFormatUnusable')).toBeInTheDocument()
  })

  it('labels every format option', () => {
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    expect(screen.getByRole('option', { name: 'config.decisionFormatSystemOne' })).toHaveValue(
      'systemone',
    )
  })

  it('removes a stored key', async () => {
    mocks.del.mockResolvedValue({})
    const changed = vi.fn()
    render(
      <ConfigSectionDecision
        config={own}
        onSave={vi.fn()}
        secretsSet={['llm_api_key_decision']}
        onSecretsChanged={changed}
      />,
    )
    fireEvent.click(screen.getByText('config.decisionRemoveKey'))
    await waitFor(() => expect(mocks.del).toHaveBeenCalledWith('llm_api_key_decision'))
    await waitFor(() => expect(changed).toHaveBeenCalled())
  })

  it('drops the typed key before it deletes the stored one', async () => {
    const order: string[] = []
    mocks.del.mockImplementation(async () => {
      order.push('delete')
      return {}
    })
    const removed = vi.fn(() => {
      order.push('discard')
    })
    const changed = vi.fn()
    render(
      <ConfigSectionDecision
        config={{ ...own, llm_api_key_decision: 'sk-typed' }}
        onSave={vi.fn()}
        secretsSet={['llm_api_key_decision']}
        onSecretsChanged={changed}
        onSecretRemoved={removed}
      />,
    )
    fireEvent.click(screen.getByText('config.decisionRemoveKey'))
    await waitFor(() => expect(changed).toHaveBeenCalled())
    expect(removed).toHaveBeenCalledWith('llm_api_key_decision')
    expect(order).toEqual(['discard', 'delete'])
  })

  it('checks the review tag against Paperless', async () => {
    mocks.getTags.mockResolvedValue({ data: { tags: [{ id: 1, name: 'other' }] } })
    render(
      <ConfigSectionDecision
        config={{ ...base, review_tag: 'ai-review' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(await screen.findByText('config.reviewTagMissing tag=ai-review')).toBeInTheDocument()
    expect(mocks.getTags).toHaveBeenCalledWith()
  })

  it('checks the trimmed name again once typing pauses', async () => {
    const { rerender } = render(
      <ConfigSectionDecision
        config={{ ...base, review_tag: ' ai-review ' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    expect(await screen.findByText('config.reviewTagPresent tag=ai-review')).toBeInTheDocument()

    rerender(
      <ConfigSectionDecision
        config={{ ...base, review_tag: 'needs-check' }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )
    await act(() => new Promise((resolve) => setTimeout(resolve, 200)))
    expect(mocks.getTags).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/config\.reviewTag(Present|Missing)/)).not.toBeInTheDocument()
    expect(await screen.findByText('config.reviewTagMissing tag=needs-check')).toBeInTheDocument()
    expect(mocks.getTags).toHaveBeenCalledTimes(3)
    expect(mocks.getTags).toHaveBeenLastCalledWith(true)
  })

  it('asks Paperless again before calling the tag missing', async () => {
    mocks.getTags
      .mockResolvedValueOnce({ data: { tags: [{ id: 1, name: 'other' }] } })
      .mockResolvedValueOnce({
        data: {
          tags: [
            { id: 1, name: 'other' },
            { id: 2, name: 'ai-review' },
          ],
        },
      })
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    expect(await screen.findByText('config.reviewTagPresent tag=ai-review')).toBeInTheDocument()
    expect(mocks.getTags.mock.calls).toEqual([[], [true]])
  })

  it('says it could not check the tag when Paperless does not answer', async () => {
    mocks.getTags.mockRejectedValue(new Error('down'))
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    expect(await screen.findByText('config.reviewTagUnknown')).toBeInTheDocument()
    expect(screen.queryByText(/config\.reviewTagMissing/)).not.toBeInTheDocument()
  })

  it('runs the probe and shows the result or the fallback', async () => {
    mocks.testDecision.mockResolvedValue({
      data: {
        success: true,
        method: 'ollama_letters',
        model: 'qwen2.5:7b',
        choice: 'Stadtwerke Saarbrücken',
        probability: 0.998,
        request: '[user] ...',
        review_tag: { name: 'ai-review', exists: true },
      },
    })
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    fireEvent.click(screen.getByText('config.decisionTest'))
    expect(
      await screen.findByText(
        'config.decisionTestOk method=ollama_letters model=qwen2.5:7b choice=Stadtwerke Saarbrücken p=99.8%',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText('[user] ...')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('decision.note.showRequest'))
    expect(screen.getByText('[user] ...')).toBeInTheDocument()
    expect(screen.getByText('decision.note.hideRequest')).toBeInTheDocument()

    mocks.testDecision.mockResolvedValue({
      data: {
        success: false,
        fallback_reason: 'provider_unsupported',
        fallback_detail: null,
        review_tag: { name: 'ai-review', exists: true },
      },
    })
    fireEvent.click(screen.getByText('config.decisionTest'))
    expect(
      await screen.findByText(
        'config.decisionTestFallback reason=decision.fallback.provider_unsupported',
      ),
    ).toBeInTheDocument()
  })

  it('shows the fallback detail and a probe that could not check the tag', async () => {
    mocks.testDecision.mockResolvedValue({
      data: {
        success: false,
        fallback_reason: 'unsupported_parameter',
        fallback_detail: 'HTTP 400: top_logprobs is not supported',
        request: null,
        review_tag: { name: 'ai-review', exists: null },
      },
    })
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    expect(await screen.findByText('config.reviewTagPresent tag=ai-review')).toBeInTheDocument()
    fireEvent.click(screen.getByText('config.decisionTest'))
    expect(await screen.findByText('HTTP 400: top_logprobs is not supported')).toBeInTheDocument()
    expect(screen.getByText('config.reviewTagUnknown')).toBeInTheDocument()
    expect(screen.queryByText(/config\.reviewTagPresent/)).not.toBeInTheDocument()
    expect(screen.queryByText('decision.note.showRequest')).not.toBeInTheDocument()
  })

  it('shows a dash when a decided probe carries no probability', async () => {
    mocks.testDecision.mockResolvedValue({
      data: {
        success: true,
        method: 'ollama_systemone',
        model: 'nimble',
        choice: 'Rechnung',
        probability: null,
      },
    })
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    fireEvent.click(screen.getByText('config.decisionTest'))
    expect(
      await screen.findByText(
        'config.decisionTestOk method=ollama_systemone model=nimble choice=Rechnung p=–',
      ),
    ).toBeInTheDocument()
  })

  it('reports a probe request that did not go through', async () => {
    mocks.testDecision.mockResolvedValue({
      data: {
        success: true,
        method: 'ollama_letters',
        model: 'm',
        choice: 'X',
        probability: 0.95,
        request: '[user] old',
      },
    })
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    fireEvent.click(screen.getByText('config.decisionTest'))
    expect(await screen.findByText('decision.note.showRequest')).toBeInTheDocument()

    mocks.testDecision.mockRejectedValue(new Error('Network Error'))
    fireEvent.click(screen.getByText('config.decisionTest'))
    expect(
      await screen.findByText('config.decisionTestFailed message=Network Error'),
    ).toBeInTheDocument()
    // the request of the earlier probe does not belong to this failure
    expect(screen.queryByText('decision.note.showRequest')).not.toBeInTheDocument()
  })

  it('reports a probe that failed outright', async () => {
    mocks.testDecision.mockResolvedValue({
      data: { success: false, message: 'connection refused' },
    })
    render(<ConfigSectionDecision config={base} onSave={vi.fn()} secretsSet={[]} />)
    fireEvent.click(screen.getByText('config.decisionTest'))
    expect(
      await screen.findByText('config.decisionTestFailed message=connection refused'),
    ).toBeInTheDocument()
  })
})
