export const defaultApiBase = (provider: string) => {
  if (provider === 'openai') return 'https://api.openai.com/v1'
  if (provider === 'grok') return 'https://api.x.ai/v1'
  if (provider === 'openrouter') return 'https://openrouter.ai/api/v1'
  return 'http://localhost:11434'
}

const bare = (url: string) => url.trim().replace(/\/+$/, '')

// A URL that is still the old provider's default follows the provider, so the
// key for the new one is not sent to the old host. A URL of the user's own is
// left alone (null).
export const apiBaseAfterSwitch = (current: string, from: string, to: string) =>
  from !== to && bare(current) === defaultApiBase(from) ? defaultApiBase(to) : null
