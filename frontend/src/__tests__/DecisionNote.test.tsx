import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { DecisionNote } from '../components/DecisionNote'
import type { DecisionDetails } from '../api/types'

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

const base: DecisionDetails = {
  method: 'ollama_letters',
  provider: 'ollama',
  model: 'qwen2.5:7b',
  outcome: 'applied',
  reason: null,
  choice: 'Telekom',
  probability: 0.9968,
  threshold: 0.9,
  top: [{ name: 'Telekom', p: 0.9968 }],
  requests: 7,
  mass: 0.99,
  fallback_reason: null,
  fallback_detail: null,
  request: { text_chars: 120, text_sha256: 'abcd', rendered: '[user] <document text, 120 chars>' },
}

describe('DecisionNote', () => {
  it('names a decided value with its probability and model', () => {
    render(<DecisionNote decision={base} />)
    expect(
      screen.getByText(
        'decision.note.decided choice=Telekom p=99.7% threshold=90% model=qwen2.5:7b',
      ),
    ).toBeInTheDocument()
  })

  it('explains a review with the translated reason', () => {
    render(
      <DecisionNote
        decision={{ ...base, outcome: 'review', reason: 'below_threshold', probability: 0.72 }}
      />,
    )
    expect(
      screen.getByText(
        'decision.note.review reason=decision.reason.below_threshold choice=Telekom p=72.0% threshold=90%',
      ),
    ).toBeInTheDocument()
  })

  it('gives no best guess when the reason fired above the threshold', () => {
    render(
      <DecisionNote
        decision={{
          ...base,
          outcome: 'review',
          reason: 'creation_off',
          choice: 'None of these',
          probability: 0.95,
        }}
      />,
    )
    expect(
      screen.getByText('decision.note.reviewNone reason=decision.reason.creation_off'),
    ).toBeInTheDocument()
  })

  it('keeps the best guess for a named review below the threshold', () => {
    render(
      <DecisionNote
        decision={{
          ...base,
          outcome: 'review',
          reason: 'low_mass',
          choice: 'Telekom',
          probability: 0.72,
        }}
      />,
    )
    expect(
      screen.getByText(
        'decision.note.review reason=decision.reason.low_mass choice=Telekom p=72.0% threshold=90%',
      ),
    ).toBeInTheDocument()
  })

  it('never calls None of these a best guess', () => {
    render(
      <DecisionNote
        decision={{
          ...base,
          outcome: 'review',
          reason: 'below_threshold',
          choice: 'None of these',
          probability: 0.72,
        }}
      />,
    )
    expect(
      screen.getByText('decision.note.reviewNone reason=decision.reason.below_threshold'),
    ).toBeInTheDocument()
  })

  it('gives no best guess for a name at or above the threshold', () => {
    render(
      <DecisionNote
        decision={{
          ...base,
          outcome: 'review',
          reason: 'low_mass',
          choice: 'Telekom',
          probability: 0.95,
        }}
      />,
    )
    expect(
      screen.getByText('decision.note.reviewNone reason=decision.reason.low_mass'),
    ).toBeInTheDocument()
  })

  it('explains a fallback with its reason and detail', () => {
    render(
      <DecisionNote
        decision={{
          ...base,
          outcome: 'fallback',
          fallback_reason: 'no_logprobs',
          fallback_detail: '200 without logprobs',
        }}
      />,
    )
    expect(
      screen.getByText('decision.note.fallback reason=decision.fallback.no_logprobs'),
    ).toBeInTheDocument()
    expect(screen.getByText('200 without logprobs')).toBeInTheDocument()
  })

  it('unfolds the request on request', () => {
    render(
      <DecisionNote
        decision={{ ...base, request: { ...base.request, full: '[user] the whole text' } }}
        showRequest
      />,
    )
    expect(screen.queryByText('[user] the whole text')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('decision.note.showRequest'))
    expect(screen.getByText('[user] the whole text')).toBeInTheDocument()
  })

  it('shows the redacted request when there is no full one', () => {
    render(<DecisionNote decision={base} showRequest />)
    fireEvent.click(screen.getByText('decision.note.showRequest'))
    expect(screen.getByText('[user] <document text, 120 chars>')).toBeInTheDocument()
  })
})
