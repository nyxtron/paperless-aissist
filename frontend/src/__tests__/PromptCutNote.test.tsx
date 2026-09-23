import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { PromptCutNote } from '../components/PromptCutNote'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    // Show the values too, so a wrong interpolation is visible.
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${JSON.stringify(vars)}` : key,
    i18n: { language: 'en' },
  }),
}))

describe('PromptCutNote', () => {
  afterEach(() => cleanup())

  it('names how much Ollama read and the window it had', () => {
    render(<PromptCutNote cut={{ evaluated: 2050, window: 4096 }} />)

    expect(
      screen.getByText('processing.promptCut {"evaluated":2050,"window":4096}'),
    ).toBeInTheDocument()
  })

  it('still warns when the window is not known', () => {
    render(<PromptCutNote cut={{ evaluated: 2050, window: null }} />)

    expect(
      screen.getByText('processing.promptCutNoWindow {"evaluated":2050}'),
    ).toBeInTheDocument()
  })
})
