import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { ConfigSectionLLM } from '../components/ConfigSectionLLM'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('ConfigSectionLLM', () => {
  it('offers OpenRouter with OpenRouter defaults', () => {
    render(
      <ConfigSectionLLM config={{ llm_provider: 'openrouter' }} onSave={vi.fn()} secretsSet={[]} />,
    )

    expect(screen.getByRole('option', { name: 'OpenRouter' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('openai/gpt-4o-mini')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('https://openrouter.ai/api/v1')).toBeInTheDocument()
  })

  it('renders configurable generation parameters', () => {
    render(
      <ConfigSectionLLM
        config={{
          llm_provider: 'openrouter',
          llm_temperature: '0.4',
          llm_max_tokens: '512',
          llm_num_ctx: '16384',
        }}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )

    expect(screen.getByText('config.llmTemperature')).toBeInTheDocument()
    expect(screen.getByDisplayValue('0.4')).toBeInTheDocument()
    expect(screen.getByText('config.llmMaxTokens')).toBeInTheDocument()
    expect(screen.getByDisplayValue('512')).toBeInTheDocument()
    expect(screen.getByText('config.llmContextWindow')).toBeInTheDocument()
    expect(screen.getByDisplayValue('16384')).toBeInTheDocument()
  })

  it('moves a default URL along when the provider changes', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <ConfigSectionLLM
        config={{ llm_provider: 'ollama', llm_api_base: 'http://localhost:11434' }}
        onSave={onSave}
        secretsSet={[]}
      />,
    )
    fireEvent.change(screen.getByDisplayValue('Ollama'), { target: { value: 'openai' } })
    expect(onSave).toHaveBeenCalledWith('llm_provider', 'openai')
    expect(onSave).toHaveBeenCalledWith('llm_api_base', 'https://api.openai.com/v1')
  })

  it('leaves a URL of your own alone when the provider changes', () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <ConfigSectionLLM
        config={{ llm_provider: 'ollama', llm_api_base: 'http://nas:11434' }}
        onSave={onSave}
        secretsSet={[]}
      />,
    )
    fireEvent.change(screen.getByDisplayValue('Ollama'), { target: { value: 'openai' } })
    expect(onSave.mock.calls).toEqual([['llm_provider', 'openai']])
  })
})
