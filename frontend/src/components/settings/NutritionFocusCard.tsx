import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { api } from '../../lib/api'
import {
  type NutritionFocusPreset,
  type NutritionFocusSettings,
} from './types'

const PRESET_METRICS: Record<Exclude<NutritionFocusPreset, 'custom'>, string[]> = {
  ldl_support: ['calories', 'saturated_fat_g', 'soluble_fiber_g', 'sodium_mg', 'protein_g'],
  performance: ['calories', 'protein_g', 'carbohydrates_g', 'fat_g'],
  comprehensive: [
    'calories', 'protein_g', 'carbohydrates_g', 'fat_g', 'saturated_fat_g',
    'soluble_fiber_g', 'sodium_mg', 'sugars_g', 'added_sugars_g', 'cholesterol_mg',
  ],
}

export function NutritionFocusCard() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery<NutritionFocusSettings>({
    queryKey: ['settings', 'nutrition-focus'],
    queryFn: () => api.get('/settings/nutrition-focus'),
  })
  const [draft, setDraft] = useState<{ preset: NutritionFocusPreset; metrics: string[] } | null>(null)
  const preset = draft?.preset ?? data?.preset ?? 'ldl_support'
  const metrics = draft?.metrics ?? data?.metrics ?? PRESET_METRICS.ldl_support

  const mutation = useMutation({
    mutationFn: () => api.put<NutritionFocusSettings>('/settings/nutrition-focus', { preset, metrics }),
    onSuccess: (saved) => {
      setDraft({ preset: saved.preset, metrics: saved.metrics })
      queryClient.setQueryData(['settings', 'nutrition-focus'], saved)
      queryClient.setQueryData(['nutrition-focus'], saved)
      queryClient.invalidateQueries({ queryKey: ['today'] })
      queryClient.invalidateQueries({ queryKey: ['nutrition-history'] })
    },
  })

  const selectPreset = (next: NutritionFocusPreset) => {
    setDraft({
      preset: next,
      metrics: next === 'custom' ? metrics : PRESET_METRICS[next],
    })
  }

  const toggleMetric = (id: string) => {
    setDraft({
      preset: 'custom',
      metrics: metrics.includes(id)
        ? metrics.filter((metric) => metric !== id)
        : [...metrics, id],
    })
  }

  return (
    <div className="glass settings-card" style={{ padding: 24 }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>Nutrition focus</div>
      <p style={{ color: 'var(--fg-tertiary)', fontSize: 14, margin: '0 0 18px' }}>
        Save the nutrition signals you want Luma to emphasize across your dashboard, plans, and coaching.
      </p>

      <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="eyebrow" style={{ fontSize: 10 }}>Focus preset</span>
        <select
          value={preset}
          disabled={isLoading || mutation.isPending}
          onChange={(event) => selectPreset(event.target.value as NutritionFocusPreset)}
          style={{
            width: '100%', padding: '10px 12px', borderRadius: 12,
            border: '1px solid var(--glass-edge)', background: 'var(--glass-1)',
            color: 'var(--fg-primary)', fontFamily: 'var(--font-sans)', fontSize: 14,
          }}
        >
          {(data?.presets ?? [
            { id: 'ldl_support', label: 'LDL support', description: '' },
            { id: 'performance', label: 'Performance macros', description: '' },
            { id: 'comprehensive', label: 'All nutrition', description: '' },
            { id: 'custom', label: 'Custom', description: '' },
          ]).map((option) => (
            <option key={option.id} value={option.id}>{option.label}</option>
          ))}
        </select>
      </label>

      {preset === 'custom' && (
        <div style={{ marginTop: 18 }}>
          <div className="eyebrow" style={{ fontSize: 10, marginBottom: 8 }}>Metrics to emphasize</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8 }}>
            {(data?.available_metrics ?? []).map((metric) => {
              const selected = metrics.includes(metric.id)
              return (
                <button
                  key={metric.id}
                  type="button"
                  role="checkbox"
                  aria-checked={selected}
                  onClick={() => toggleMetric(metric.id)}
                  disabled={mutation.isPending}
                  style={{
                    padding: '9px 10px', borderRadius: 10, textAlign: 'left',
                    border: `1px solid ${selected ? 'rgba(56,189,248,0.45)' : 'var(--glass-edge)'}`,
                    background: selected ? 'rgba(56,189,248,0.10)' : 'var(--glass-1)',
                    color: selected ? 'var(--fg-primary)' : 'var(--fg-tertiary)',
                    cursor: mutation.isPending ? 'not-allowed' : 'pointer', fontSize: 12,
                  }}
                >
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    {selected && <Check size={13} aria-hidden="true" />}
                    {metric.label}
                  </span>
                </button>
              )
            })}
          </div>
          {metrics.length === 0 && (
            <p style={{ color: 'var(--bad)', fontSize: 12, margin: '10px 0 0' }}>Choose at least one metric.</p>
          )}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
        <span style={{ color: mutation.isError ? 'var(--bad)' : 'var(--fg-quiet)', fontSize: 12 }}>
          {mutation.isError ? (mutation.error as Error).message : `${metrics.length} metric${metrics.length === 1 ? '' : 's'} selected`}
        </span>
        <button
          type="button"
          className="btn btn-primary"
          disabled={isLoading || mutation.isPending || metrics.length === 0}
          onClick={() => mutation.mutate()}
          style={{ padding: '8px 18px', fontSize: 13 }}
        >
          {mutation.isPending ? 'Saving…' : 'Save focus'}
        </button>
      </div>
    </div>
  )
}
