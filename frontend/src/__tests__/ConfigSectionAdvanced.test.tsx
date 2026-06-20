import { beforeEach, describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { AxiosResponse } from 'axios'

import { ConfigSectionAdvanced } from '../components/ConfigSectionAdvanced'
import { configApi } from '../api/client'

const { mockToastError } = vi.hoisted(() => ({
  mockToastError: vi.fn(),
}))

vi.mock('../api/client', () => ({
  configApi: {
    generateAutomationToken: vi.fn(),
    revokeAutomationToken: vi.fn(),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    error: mockToastError,
  },
}))

function mockAxiosResponse<T>(data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  } as AxiosResponse<T>
}

describe('ConfigSectionAdvanced', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
      configurable: true,
    })
  })

  it('renders MCP toggle and calls handleChange on change', () => {
    const onSave = vi.fn()

    // auth_enabled=true → its select shows 'common.enabled'
    // mcp_enabled=false → its select shows 'common.disabled' (unique among all selects)
    render(
      <ConfigSectionAdvanced
        config={{ auth_enabled: 'true', mcp_enabled: 'false' }}
        onSave={onSave}
      />,
    )

    expect(screen.getByText('config.mcpEnabled')).toBeInTheDocument()

    const select = screen.getByDisplayValue('common.disabled')
    fireEvent.change(select, { target: { value: 'true' } })

    expect(onSave).toHaveBeenCalledWith('mcp_enabled', 'true')
  })

  it('saves document list refresh mode changes', () => {
    const onSave = vi.fn()

    render(
      <ConfigSectionAdvanced
        config={{ document_list_refresh_mode: 'automatic' }}
        onSave={onSave}
      />,
    )

    fireEvent.change(screen.getByLabelText('config.documentListRefreshMode'), {
      target: { value: 'manual' },
    })

    expect(onSave).toHaveBeenCalledWith('document_list_refresh_mode', 'manual')
  })

  it('shows automation token status from secret metadata', () => {
    render(
      <ConfigSectionAdvanced
        config={{}}
        onSave={vi.fn()}
        secretsSet={['automation_api_token_hash']}
      />,
    )

    expect(screen.getByText('config.automationTokenConfigured')).toBeInTheDocument()
  })

  it('generates and displays a one-time automation token', async () => {
    vi.mocked(configApi.generateAutomationToken).mockResolvedValue(
      mockAxiosResponse({ token: 'paia_test_token' }),
    )
    const onSecretsChanged = vi.fn()

    render(
      <ConfigSectionAdvanced
        config={{}}
        onSave={vi.fn()}
        secretsSet={[]}
        onSecretsChanged={onSecretsChanged}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'config.generateAutomationToken' }))

    await waitFor(() => {
      expect(screen.getByDisplayValue('paia_test_token')).toBeInTheDocument()
    })
    expect(onSecretsChanged).toHaveBeenCalled()
  })

  it('copies the automation token through a fallback when clipboard api is unavailable', async () => {
    vi.mocked(configApi.generateAutomationToken).mockResolvedValue(
      mockAxiosResponse({ token: 'paia_test_token' }),
    )
    const execCommand = vi.fn(() => true)
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    })
    Object.defineProperty(document, 'execCommand', {
      value: execCommand,
      configurable: true,
    })

    render(
      <ConfigSectionAdvanced
        config={{}}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'config.generateAutomationToken' }))
    await screen.findByDisplayValue('paia_test_token')

    fireEvent.click(screen.getByRole('button', { name: 'config.copyAutomationToken' }))

    await waitFor(() => {
      expect(execCommand).toHaveBeenCalledWith('copy')
    })
    expect(screen.getByRole('button', { name: 'config.copiedAutomationToken' })).toBeInTheDocument()
  })

  it('does not show copied when clipboard and fallback copy fail', async () => {
    vi.mocked(configApi.generateAutomationToken).mockResolvedValue(
      mockAxiosResponse({ token: 'paia_test_token' }),
    )
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: vi.fn().mockRejectedValue(new Error('denied')),
      },
      configurable: true,
    })
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => false),
      configurable: true,
    })

    render(
      <ConfigSectionAdvanced
        config={{}}
        onSave={vi.fn()}
        secretsSet={[]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'config.generateAutomationToken' }))
    await screen.findByDisplayValue('paia_test_token')

    fireEvent.click(screen.getByRole('button', { name: 'config.copyAutomationToken' }))

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('config.copyAutomationTokenFailed')
    })
    expect(screen.queryByRole('button', { name: 'config.copiedAutomationToken' })).not.toBeInTheDocument()
  })

  it('revokes the automation token', async () => {
    vi.mocked(configApi.revokeAutomationToken).mockResolvedValue(
      mockAxiosResponse({ success: true }),
    )
    const onSecretsChanged = vi.fn()

    render(
      <ConfigSectionAdvanced
        config={{}}
        onSave={vi.fn()}
        secretsSet={['automation_api_token_hash']}
        onSecretsChanged={onSecretsChanged}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'config.revokeAutomationToken' }))

    await waitFor(() => {
      expect(configApi.revokeAutomationToken).toHaveBeenCalled()
    })
    expect(onSecretsChanged).toHaveBeenCalled()
  })
})
