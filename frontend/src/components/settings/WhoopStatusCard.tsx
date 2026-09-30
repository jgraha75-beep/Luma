import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'

type WhoopObservation = {
  external_id: string
  start: string | null
  end: string | null
  score_state: string | null
  pulled_at: string | null
  recovery_score?: number
  sleep_performance_percentage?: number
  strain?: number
  sport_name?: string
  height_meter?: number
  weight_kilogram?: number
  max_heart_rate?: number
}

export type WhoopStatus = {
  source: 'whoop'
  separate_from_apple_health: true
  quality: 'unknown' | 'complete' | 'partial' | 'stale'
  reasons: string[]
  sync: null | {
    status: 'complete' | 'partial' | 'error'
    pulled_at: string
    window_start: string | null
    window_end: string | null
    collections: Record<string, unknown>
  }
  latest: Record<'recovery' | 'sleep' | 'cycle' | 'workout' | 'body_measurement', WhoopObservation | null>
}

const QUALITY_LABELS: Record<WhoopStatus['quality'], string> = {
  unknown: 'Not synced',
  complete: 'Current',
  partial: 'Partial',
  stale: 'Stale',
}

function valueOrDash(value: number | undefined, suffix: string): string {
  return typeof value === 'number' ? `${value}${suffix}` : '—'
}

function WhoopRow({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16, padding: '10px 0', borderBottom: '1px solid var(--glass-edge)' }}>
      <span style={{ color: 'var(--fg-tertiary)', fontSize: 13 }}>{label}</span>
      <span style={{ color: 'var(--fg-primary)', fontSize: 13, fontWeight: 500, textAlign: 'right' }}>
        {value}
        {detail && <span style={{ display: 'block', color: 'var(--fg-quiet)', fontSize: 11, fontWeight: 400, marginTop: 2 }}>{detail}</span>}
      </span>
    </div>
  )
}

export function WhoopStatusCard() {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const { data, isLoading, refetch } = useQuery<WhoopStatus>({
    queryKey: ['whoop', 'status'],
    queryFn: () => api.get('/whoop/status'),
    refetchInterval: 60000,
  })
  const importMutation = useMutation({
    mutationFn: (bundle: Record<string, unknown>) => api.post('/whoop/import', bundle),
    onSuccess: async () => {
      setImportError(null)
      await queryClient.invalidateQueries({ queryKey: ['whoop', 'status'] })
    },
    onError: (error: Error) => setImportError(error.message),
  })

  const recovery = data?.latest.recovery
  const sleep = data?.latest.sleep
  const cycle = data?.latest.cycle
  const workout = data?.latest.workout
  const body = data?.latest.body_measurement
  const recoveryValue = recovery?.score_state === 'SCORED'
    ? valueOrDash(recovery.recovery_score, '%')
    : recovery ? 'Score pending' : '—'
  const workoutValue = workout
    ? `${workout.sport_name ?? 'Workout'} · ${valueOrDash(workout.strain, ' strain')}`
    : '—'
  const bodyValue = body
    ? [
        typeof body.weight_kilogram === 'number' ? `${body.weight_kilogram.toFixed(1)} kg` : null,
        typeof body.height_meter === 'number' ? `${body.height_meter.toFixed(2)} m` : null,
        typeof body.max_heart_rate === 'number' ? `${body.max_heart_rate} bpm max` : null,
      ].filter(Boolean).join(' · ') || '—'
    : '—'

  const handleBundleSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const parsed: unknown = JSON.parse(await file.text())
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('WHOOP bundle must be a JSON object.')
      }
      importMutation.mutate(parsed as Record<string, unknown>)
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'Unable to read WHOOP bundle.')
    }
  }

  return (
    <section className="glass settings-card" style={{ padding: 24 }} aria-labelledby="whoop-status-title">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 8 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Supplemental source</div>
          <h3 id="whoop-status-title" style={{ fontSize: 15, margin: 0, color: 'var(--fg-primary)' }}>WHOOP</h3>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: data?.quality === 'complete' ? 'var(--good)' : 'var(--fg-tertiary)', fontSize: 11, fontWeight: 600 }}>
            {data ? QUALITY_LABELS[data.quality] : isLoading ? 'Loading' : 'Unavailable'}
          </span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button type="button" className="btn" onClick={() => refetch()} disabled={isLoading || importMutation.isPending} style={{ padding: '6px 10px', fontSize: 11 }}>
              Refresh
            </button>
            <button type="button" className="btn" onClick={() => fileInputRef.current?.click()} disabled={importMutation.isPending} style={{ padding: '6px 10px', fontSize: 11 }}>
              {importMutation.isPending ? 'Importing…' : 'Import'}
            </button>
            <input ref={fileInputRef} type="file" accept="application/json,.json" onChange={handleBundleSelected} style={{ display: 'none' }} aria-label="Import WHOOP JSON bundle" />
          </div>
        </div>
      </div>

      <p style={{ margin: '0 0 10px', color: 'var(--fg-tertiary)', fontSize: 12, lineHeight: 1.5 }}>
        WHOOP recovery and strain stay separate from Apple Health metrics. They are context, not a combined fatigue score.
      </p>

      {data ? (
        <div>
          <WhoopRow label="Recovery" value={recoveryValue} detail={recovery?.score_state ?? undefined} />
          <WhoopRow label="Sleep performance" value={valueOrDash(sleep?.sleep_performance_percentage, '%')} detail={sleep?.score_state ?? undefined} />
          <WhoopRow label="Cycle strain" value={valueOrDash(cycle?.strain, '')} detail={cycle?.score_state ?? undefined} />
          <WhoopRow label="Latest workout" value={workoutValue} detail={workout?.score_state ?? undefined} />
          <WhoopRow label="Body measurements" value={bodyValue} detail={body ? 'WHOOP profile data' : undefined} />
          <div style={{ paddingTop: 10, color: 'var(--fg-quiet)', fontSize: 11 }}>
            {data.sync ? `Last synced ${new Date(data.sync.pulled_at).toLocaleString()}` : 'No WHOOP sync has been imported yet.'}
            {data.reasons.length > 0 && <span style={{ display: 'block', marginTop: 4 }}>{data.reasons.join(' · ')}</span>}
            {importError && <span role="alert" style={{ display: 'block', marginTop: 4, color: 'var(--bad)' }}>{importError}</span>}
          </div>
        </div>
      ) : (
        <div style={{ color: 'var(--fg-quiet)', fontSize: 13, paddingTop: 8 }}>
          {isLoading ? 'Loading WHOOP status…' : 'WHOOP status is unavailable.'}
        </div>
      )}
    </section>
  )
}
