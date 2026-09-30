import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { type HaeImportSettings } from './types'

export function HaeImportCard() {
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)
  const [copiedSecret, setCopiedSecret] = useState(false)
  const [confirmRegenerate, setConfirmRegenerate] = useState(false)

  const { data, isLoading } = useQuery<HaeImportSettings>({
    queryKey: ['settings', 'hae-import'],
    queryFn: () => api.get('/settings/hae-import'),
  })

  const regenerateMutation = useMutation({
    mutationFn: () => api.post<HaeImportSettings>('/settings/hae-import/regenerate'),
    onSuccess: (newData) => {
      queryClient.setQueryData(['settings', 'hae-import'], newData)
      setConfirmRegenerate(false)
    },
  })

  const webhookUrl = data
    ? `${window.location.origin}/api/v1/ingest/hae/${data.token}`
    : ''

  const handleCopy = async () => {
    if (!webhookUrl) return
    await navigator.clipboard.writeText(webhookUrl)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  const handleCopySecret = async () => {
    if (!data?.app_secret) return
    await navigator.clipboard.writeText(data.app_secret)
    setCopiedSecret(true)
    window.setTimeout(() => setCopiedSecret(false), 2000)
  }

  return (
    <div className="glass settings-card" style={{ padding: 24 }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>Health import</div>
      <p style={{ color: 'var(--fg-tertiary)', fontSize: 14, margin: '0 0 16px' }}>
        In Health Auto Export, go to Automations &rarr; New Automation &rarr; REST API and add both values below.
        The URL identifies you; the header secret authenticates the app.
      </p>

      <div style={{ margin: '0 0 18px', paddingBottom: 16, borderBottom: '1px solid var(--glass-edge)' }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-primary)', marginBottom: 10 }}>
          Required export settings
        </div>
        <dl
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(120px, 0.8fr) minmax(140px, 1fr)',
            gap: '7px 16px',
            margin: 0,
            fontSize: 13,
          }}
        >
          <dt style={{ color: 'var(--fg-tertiary)' }}>Automation type</dt><dd style={{ margin: 0 }}>REST API</dd>
          <dt style={{ color: 'var(--fg-tertiary)' }}>Data type</dt><dd style={{ margin: 0 }}>Health Metrics</dd>
          <dt style={{ color: 'var(--fg-tertiary)' }}>Format</dt><dd style={{ margin: 0 }}>JSON</dd>
          <dt style={{ color: 'var(--fg-tertiary)' }}>Export version</dt><dd style={{ margin: 0 }}>Version 2</dd>
          <dt style={{ color: 'var(--fg-tertiary)' }}>Date range</dt><dd style={{ margin: 0 }}>Since Last Sync</dd>
          <dt style={{ color: 'var(--fg-tertiary)' }}>Summarize data</dt><dd style={{ margin: 0 }}>On · daily</dd>
          <dt style={{ color: 'var(--fg-tertiary)' }}>Large exports</dt><dd style={{ margin: 0 }}>Batch requests on</dd>
        </dl>
        <p style={{ color: 'var(--fg-tertiary)', fontSize: 12, margin: '12px 0 0' }}>
          Keep Tailscale connected on the iPhone. For the first manual test, choose Previous 7 Days and keep the phone unlocked or connected through iPhone Mirroring.
        </p>
      </div>

      {isLoading ? (
        <p style={{ fontSize: 13, color: 'var(--fg-quiet)', margin: 0 }}>Loading…</p>
      ) : data ? (
        <>
          <div style={{ marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--fg-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Endpoint URL
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              aria-label="Health Auto Export endpoint URL"
              readOnly
              value={webhookUrl}
              style={{
                flex: 1,
                minWidth: 0,
                fontSize: 12,
                fontFamily: 'var(--font-mono, monospace)',
                padding: '8px 10px',
                borderRadius: 10,
                border: '1px solid var(--glass-edge)',
                background: 'var(--glass-1)',
                color: 'var(--fg-primary)',
                outline: 'none',
              }}
            />
            <button
              type="button"
              className="btn"
              onClick={handleCopy}
              style={{ padding: '8px 14px', fontSize: 12, flexShrink: 0 }}
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>

          {data.app_secret && (
            <>
              <div style={{ marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: 'var(--fg-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Header — X-HAE-Signature
                </span>
              </div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <input
                  aria-label="Health Auto Export app secret"
                  readOnly
                  type="password"
                  value={data.app_secret}
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 12,
                    fontFamily: 'var(--font-mono, monospace)',
                    padding: '8px 10px',
                    borderRadius: 10,
                    border: '1px solid var(--glass-edge)',
                    background: 'var(--glass-1)',
                    color: 'var(--fg-primary)',
                    outline: 'none',
                  }}
                />
                <button
                  type="button"
                  className="btn"
                  onClick={handleCopySecret}
                  style={{ padding: '8px 14px', fontSize: 12, flexShrink: 0 }}
                >
                  {copiedSecret ? 'Copied' : 'Copy'}
                </button>
              </div>
            </>
          )}

          {confirmRegenerate ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <p style={{ fontSize: 13, color: 'var(--bad)', margin: 0 }}>
                The old URL will stop working immediately. Update Health Auto Export before regenerating.
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => regenerateMutation.mutate()}
                  disabled={regenerateMutation.isPending}
                  style={{ fontSize: 12, padding: '8px 14px' }}
                >
                  {regenerateMutation.isPending ? 'Regenerating…' : 'Yes, regenerate'}
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setConfirmRegenerate(false)}
                  style={{ fontSize: 12, padding: '8px 14px' }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="btn"
              onClick={() => setConfirmRegenerate(true)}
              style={{ fontSize: 12, padding: '8px 14px' }}
            >
              Regenerate URL
            </button>
          )}
        </>
      ) : (
        <p style={{ fontSize: 13, color: 'var(--fg-quiet)', margin: 0 }}>Unable to load import token.</p>
      )}
    </div>
  )
}
