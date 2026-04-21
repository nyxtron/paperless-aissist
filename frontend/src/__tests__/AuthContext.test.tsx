import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../contexts/AuthContext'

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    get: mockGet,
    post: mockPost,
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  configApi: {},
  documentsApi: {},
  statsApi: {},
  schedulerApi: {},
  promptsApi: {},
}))

function TestComponent() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="loading">{String(auth.loading)}</span>
      <span data-testid="isAuthEnabled">{String(auth.isAuthEnabled)}</span>
      <span data-testid="isAuthenticated">{String(auth.isAuthenticated)}</span>
      <span data-testid="token">{String(auth.token)}</span>
    </div>
  )
}

function createMockResponse(data: any) {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {},
  }
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorage.clear()
    mockGet.mockReset()
    mockPost.mockReset()
    mockGet.mockResolvedValue(createMockResponse({ auth_enabled: false }))
    mockPost.mockResolvedValue(createMockResponse({}))
  })

  it('renders children', () => {
    mockGet.mockResolvedValueOnce(createMockResponse({ auth_enabled: false }))

    render(
      <AuthProvider>
        <div>Child content</div>
      </AuthProvider>,
    )
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('starts with loading=true', async () => {
    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>,
    )
    expect(screen.getByTestId('loading').textContent).toBe('true')
  })

  it('sets isAuthenticated=true when auth is disabled', async () => {
    mockGet.mockResolvedValueOnce(createMockResponse({ auth_enabled: false }))

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    expect(screen.getByTestId('isAuthEnabled').textContent).toBe('false')
    expect(screen.getByTestId('isAuthenticated').textContent).toBe('true')
  })

  it('sets isAuthenticated=false when auth is enabled and no token stored', async () => {
    mockGet.mockResolvedValueOnce(createMockResponse({ auth_enabled: true }))

    render(
      <AuthProvider>
        <TestComponent />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('isAuthEnabled').textContent).toBe('true')
    })

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    await waitFor(() => {
      expect(screen.getByTestId('isAuthenticated').textContent).toBe('false')
    })
  })

  it('login stores token and sets isAuthenticated=true', async () => {
    mockGet.mockResolvedValueOnce(createMockResponse({ auth_enabled: true }))

    function TestComponentWithLogin() {
      const auth = useAuth()

      return (
        <div>
          <span data-testid="loading">{String(auth.loading)}</span>
          <span data-testid="isAuthEnabled">{String(auth.isAuthEnabled)}</span>
          <span data-testid="isAuthenticated">{String(auth.isAuthenticated)}</span>
          <span data-testid="token">{String(auth.token)}</span>
          <button onClick={() => auth.login('test-token-123')}>Login</button>
        </div>
      )
    }

    render(
      <AuthProvider>
        <TestComponentWithLogin />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('isAuthEnabled').textContent).toBe('true')
    })

    await waitFor(() => {
      expect(screen.getByTestId('isAuthenticated').textContent).toBe('false')
    })

    act(() => {
      screen.getByRole('button', { name: 'Login' }).click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('isAuthenticated').textContent).toBe('true')
    })
    expect(screen.getByTestId('token').textContent).toBe('test-token-123')
    expect(localStorage.setItem).toHaveBeenCalledWith('paperless_token', 'test-token-123')
  })

  it('logout removes token and sets isAuthenticated=false', async () => {
    vi.mocked(localStorage.getItem).mockReturnValueOnce('existing-token')
    mockGet.mockResolvedValueOnce(createMockResponse({ auth_enabled: true }))

    function TestComponentWithLogout() {
      const auth = useAuth()

      return (
        <div>
          <span data-testid="loading">{String(auth.loading)}</span>
          <span data-testid="isAuthEnabled">{String(auth.isAuthEnabled)}</span>
          <span data-testid="isAuthenticated">{String(auth.isAuthenticated)}</span>
          <span data-testid="token">{String(auth.token)}</span>
          <button onClick={() => auth.logout()}>Logout</button>
        </div>
      )
    }

    render(
      <AuthProvider>
        <TestComponentWithLogout />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('isAuthEnabled').textContent).toBe('true')
    })

    await waitFor(() => {
      expect(screen.getByTestId('isAuthenticated').textContent).toBe('true')
    })

    await act(async () => {
      await screen.getByRole('button', { name: 'Logout' }).click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('isAuthenticated').textContent).toBe('false')
    })
    expect(screen.getByTestId('token').textContent).toBe('null')
    expect(localStorage.removeItem).toHaveBeenCalledWith('paperless_token')
  })
})
