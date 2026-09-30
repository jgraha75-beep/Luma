import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { HealthConnectCard } from '../components/settings/HealthConnectCard'
import { HaeImportCard } from '../components/settings/HaeImportCard'
import { DataSourcePicker } from '../components/settings/DataSourcePicker'
import { WhoopStatusCard, type WhoopStatus } from '../components/settings/WhoopStatusCard'
import { api, type User } from '../lib/api'

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false }, mutations: { retry: false } },
  })
}

function wrap(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('HealthConnectCard', () => {
  it('renders the health-connect endpoint URL from the import token', () => {
    const client = makeClient()
    client.setQueryData(['settings', 'hae-import'], { token: 'tok-123', app_secret: 's' })

    render(<HealthConnectCard />, { wrapper: wrap(client) })

    const input = screen.getByLabelText('Health Connect endpoint URL') as HTMLInputElement
    expect(input.value).toContain('/api/v1/ingest/health-connect/tok-123')
    expect(input.value).not.toContain('/ingest/hae/')
  })
})

describe('HaeImportCard', () => {
  it('shows the exact Health Auto Export REST configuration', () => {
    const client = makeClient()
    client.setQueryData(['settings', 'hae-import'], { token: 'tok-123', app_secret: 'secret' })

    render(<HaeImportCard />, { wrapper: wrap(client) })

    expect(screen.getByText('REST API')).toBeInTheDocument()
    expect(screen.getByText('JSON')).toBeInTheDocument()
    expect(screen.getByText('Version 2')).toBeInTheDocument()
    expect(screen.getByText('Since Last Sync')).toBeInTheDocument()
    expect(screen.getByText('Batch requests on')).toBeInTheDocument()
  })
})

describe('DataSourcePicker', () => {
  const baseUser: User = {
    id: 'u1', email: 'a@b.c', display_name: 'A', role: 'operator', data_source: 'apple_health',
  }

  it('reflects the current data_source selection', () => {
    const client = makeClient()
    client.setQueryData(['me'], baseUser)

    render(<DataSourcePicker />, { wrapper: wrap(client) })

    expect(screen.getByRole('radio', { name: /Apple Health/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: /Health Connect/ })).toHaveAttribute('aria-checked', 'false')
  })

  it('patches /auth/me when switching source', async () => {
    const client = makeClient()
    client.setQueryData(['me'], baseUser)
    const patch = vi.spyOn(api, 'patch').mockResolvedValue({ ...baseUser, data_source: 'health_connect' })

    render(<DataSourcePicker />, { wrapper: wrap(client) })
    fireEvent.click(screen.getByRole('radio', { name: /Health Connect/ }))

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith('/auth/me', { data_source: 'health_connect' })
    })
  })

  it('does not re-patch when clicking the already-active source', () => {
    const client = makeClient()
    client.setQueryData(['me'], baseUser)
    const patch = vi.spyOn(api, 'patch').mockResolvedValue(baseUser)

    render(<DataSourcePicker />, { wrapper: wrap(client) })
    fireEvent.click(screen.getByRole('radio', { name: /Apple Health/ }))

    expect(patch).not.toHaveBeenCalled()
  })
})

describe('WhoopStatusCard', () => {
  it('keeps WHOOP scores explicitly separate from Apple Health', () => {
    const client = makeClient()
    const status: WhoopStatus = {
      source: 'whoop',
      separate_from_apple_health: true,
      quality: 'complete',
      reasons: [],
      sync: {
        status: 'complete',
        pulled_at: '2026-09-01T20:30:00Z',
        window_start: '2026-08-25T00:00:00Z',
        window_end: '2026-09-01T20:30:00Z',
        collections: {},
      },
      latest: {
        recovery: { external_id: '1', start: null, end: null, score_state: 'SCORED', pulled_at: '2026-09-01T20:30:00Z', recovery_score: 73 },
        sleep: { external_id: '2', start: null, end: null, score_state: 'SCORED', pulled_at: '2026-09-01T20:30:00Z', sleep_performance_percentage: 84 },
        cycle: { external_id: '3', start: null, end: null, score_state: 'SCORED', pulled_at: '2026-09-01T20:30:00Z', strain: 10.8 },
        workout: { external_id: '4', start: null, end: null, score_state: 'SCORED', pulled_at: '2026-09-01T20:30:00Z', sport_name: 'Dance', strain: 12.1 },
      },
    }
    client.setQueryData(['whoop', 'status'], status)

    render(<WhoopStatusCard />, { wrapper: wrap(client) })

    expect(screen.getByText(/stay separate from Apple Health metrics/)).toBeInTheDocument()
    expect(screen.getByText('73%')).toBeInTheDocument()
    expect(screen.getByText('Dance · 12.1 strain')).toBeInTheDocument()
  })

  it('shows an explicit unknown state before the first sync', () => {
    const client = makeClient()
    const status: WhoopStatus = {
      source: 'whoop',
      separate_from_apple_health: true,
      quality: 'unknown',
      reasons: ['WHOOP has not been synced'],
      sync: null,
      latest: { recovery: null, sleep: null, cycle: null, workout: null },
    }
    client.setQueryData(['whoop', 'status'], status)

    render(<WhoopStatusCard />, { wrapper: wrap(client) })

    expect(screen.getByText('Not synced')).toBeInTheDocument()
    expect(screen.getByText('No WHOOP sync has been imported yet.')).toBeInTheDocument()
  })
})
