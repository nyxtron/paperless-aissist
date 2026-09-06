import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThemeProvider } from '../contexts/ThemeContext'
import { ThemeSwitch } from '../components/ThemeSwitch'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('ThemeSwitch', () => {
  it('offers the three modes with system pressed by default', () => {
    render(<ThemeProvider><ThemeSwitch /></ThemeProvider>)

    expect(screen.getByLabelText('theme.system')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('theme.light')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByLabelText('theme.dark')).toHaveAttribute('aria-pressed', 'false')
  })

  it('stores and presses the chosen mode', () => {
    render(<ThemeProvider><ThemeSwitch /></ThemeProvider>)

    fireEvent.click(screen.getByLabelText('theme.dark'))

    expect(localStorage.setItem).toHaveBeenCalledWith('theme', 'dark')
    expect(screen.getByLabelText('theme.dark')).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })
})
