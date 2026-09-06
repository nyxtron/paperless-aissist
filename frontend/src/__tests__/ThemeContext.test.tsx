import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { ThemeProvider, useTheme } from '../contexts/ThemeContext'

type Listener = (event: { matches: boolean }) => void

function installMatchMedia(prefersDark: boolean) {
  const listeners: Listener[] = []
  const media = {
    matches: prefersDark,
    addEventListener: (_: string, listener: Listener) => listeners.push(listener),
    removeEventListener: (_: string, listener: Listener) => {
      const index = listeners.indexOf(listener)
      if (index >= 0) listeners.splice(index, 1)
    },
  }
  window.matchMedia = vi.fn().mockReturnValue(media) as unknown as typeof window.matchMedia
  return {
    flip(matches: boolean) {
      media.matches = matches
      listeners.forEach((listener) => listener({ matches }))
    },
  }
}

function Probe() {
  const { theme, resolved, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolved}</span>
      <button onClick={() => setTheme('dark')}>dark</button>
      <button onClick={() => setTheme('light')}>light</button>
      <button onClick={() => setTheme('system')}>system</button>
    </div>
  )
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    vi.mocked(localStorage.getItem).mockReturnValue(null)
    document.documentElement.classList.remove('dark')
    document.documentElement.style.colorScheme = ''
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to system and follows a light system', () => {
    installMatchMedia(false)
    render(<ThemeProvider><Probe /></ThemeProvider>)

    expect(screen.getByTestId('theme').textContent).toBe('system')
    expect(screen.getByTestId('resolved').textContent).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('follows a dark system', () => {
    installMatchMedia(true)
    render(<ThemeProvider><Probe /></ThemeProvider>)

    expect(screen.getByTestId('resolved').textContent).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('reacts to a system change while on system', () => {
    const media = installMatchMedia(false)
    render(<ThemeProvider><Probe /></ThemeProvider>)

    act(() => media.flip(true))

    expect(screen.getByTestId('resolved').textContent).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('stores an explicit choice and applies it', () => {
    installMatchMedia(false)
    render(<ThemeProvider><Probe /></ThemeProvider>)

    fireEvent.click(screen.getByText('dark'))

    expect(localStorage.setItem).toHaveBeenCalledWith('theme', 'dark')
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('ignores the system once a choice is made', () => {
    const media = installMatchMedia(false)
    render(<ThemeProvider><Probe /></ThemeProvider>)

    fireEvent.click(screen.getByRole('button', { name: 'light' }))
    act(() => media.flip(true))

    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })

  it('reads a stored choice on start and clears it for system', () => {
    vi.mocked(localStorage.getItem).mockReturnValue('dark')
    installMatchMedia(false)
    render(<ThemeProvider><Probe /></ThemeProvider>)

    expect(screen.getByTestId('theme').textContent).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    fireEvent.click(screen.getByText('system'))

    expect(localStorage.removeItem).toHaveBeenCalledWith('theme')
    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })

  it('treats storage errors and a missing matchMedia as system light', () => {
    vi.mocked(localStorage.getItem).mockImplementation(() => {
      throw new Error('blocked')
    })
    // @ts-expect-error jsdom has no matchMedia unless installed
    window.matchMedia = undefined
    render(<ThemeProvider><Probe /></ThemeProvider>)

    expect(screen.getByTestId('theme').textContent).toBe('system')
    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })
})
