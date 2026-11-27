import { describe, it, expect } from 'vitest'

import { apiBaseAfterSwitch, defaultApiBase } from '../components/providerDefaults'

describe('apiBaseAfterSwitch', () => {
  it.each([
    ['ollama', 'openai', 'https://api.openai.com/v1'],
    ['openai', 'grok', 'https://api.x.ai/v1'],
    ['grok', 'openrouter', 'https://openrouter.ai/api/v1'],
    ['openrouter', 'ollama', 'http://localhost:11434'],
  ])('takes the default of %s to the default of %s', (from, to, url) => {
    expect(apiBaseAfterSwitch(defaultApiBase(from), from, to)).toBe(url)
  })

  it('knows the default with a slash or blanks around it', () => {
    expect(apiBaseAfterSwitch(' http://localhost:11434/ ', 'ollama', 'openai')).toBe(
      'https://api.openai.com/v1',
    )
  })

  it.each([
    ['a URL of your own', 'http://nas:11434', 'ollama', 'openai'],
    ['an empty URL', '', 'ollama', 'openai'],
    ['the default of another provider', 'https://api.x.ai/v1', 'ollama', 'openai'],
    ['the URL when the provider stays', 'http://localhost:11434', 'ollama', 'ollama'],
  ])('leaves %s alone', (_name, current, from, to) => {
    expect(apiBaseAfterSwitch(current, from, to)).toBeNull()
  })
})
