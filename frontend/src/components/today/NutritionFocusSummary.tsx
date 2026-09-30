import type { TodayData } from '../../lib/api'
import { fmt } from '../../lib/format'
import { MacroBar } from './MacroBar'

type FocusMetric = NonNullable<TodayData['nutrition_focus']>['available_metrics'][number]
type MetricValue = NonNullable<TodayData['nutrition_adherence']>[string]

const FALLBACK_METRICS: FocusMetric[] = [
  { id: 'calories', label: 'Calories', unit: 'kcal', direction: 'info' },
  { id: 'saturated_fat_g', label: 'Saturated fat', unit: 'g', direction: 'max' },
  { id: 'soluble_fiber_g', label: 'Soluble fiber', unit: 'g', direction: 'min' },
  { id: 'sodium_mg', label: 'Sodium', unit: 'mg', direction: 'max' },
  { id: 'protein_g', label: 'Protein', unit: 'g', direction: 'min' },
]

function digitsFor(metric: FocusMetric) {
  return metric.unit === 'g' && metric.id !== 'protein_g' ? 1 : 0
}

function metricColor(metric: FocusMetric, value: MetricValue | undefined) {
  if (!value || value.target == null || value.pct == null) return 'var(--fg-primary)'
  if (metric.direction === 'max' && value.pct > 100) return 'var(--bad)'
  if (metric.direction === 'min' && value.pct < 90) return 'var(--warn)'
  return 'var(--good)'
}

export function NutritionFocusSummary({
  focus,
  adherence,
  compact = false,
}: {
  focus?: TodayData['nutrition_focus']
  adherence?: TodayData['nutrition_adherence']
  compact?: boolean
}) {
  const metricById = new Map((focus?.available_metrics ?? FALLBACK_METRICS).map((metric) => [metric.id, metric]))
  const selectedIds = focus?.metrics ?? FALLBACK_METRICS.map((metric) => metric.id)
  const selectedMetrics = selectedIds
    .map((id) => metricById.get(id))
    .filter((metric): metric is FocusMetric => metric != null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 10 : 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
        <div className="eyebrow">Nutrition focus</div>
        {focus?.preset && <span style={{ fontSize: 11, color: 'var(--fg-quiet)' }}>{focus.preset === 'custom' ? 'Custom' : focus.preset === 'performance' ? 'Performance macros' : focus.preset === 'comprehensive' ? 'All nutrition' : 'LDL support'}</span>}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: compact ? '1fr 1fr' : 'repeat(auto-fit, minmax(145px, 1fr))', gap: compact ? 8 : 10 }}>
        {selectedMetrics.map((metric) => {
          const value = adherence?.[metric.id]
          const digits = digitsFor(metric)
          const logged = value?.logged ?? 0
          const color = metricColor(metric, value)
          const targetLabel = value?.target == null ? null : `/ ${fmt(value.target, digits)} ${metric.unit}`
          return (
            <div key={metric.id} className="glass-inset" style={{ padding: compact ? '10px 11px' : '12px 13px', borderRadius: 10, minWidth: 0 }}>
              <div style={{ fontSize: 10, color: 'var(--fg-quiet)', textTransform: 'uppercase', letterSpacing: '0.06em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{metric.label}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, marginTop: 4 }}>
                <span className="num" style={{ fontSize: compact ? 20 : 22, fontWeight: 500, color }}>{fmt(logged, digits)}</span>
                <span style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>{targetLabel ?? metric.unit}</span>
              </div>
              {value?.target != null && value.target > 0 && (
                <MacroBar pct={value.pct ?? 0} color={color} glow="none" height={3} marginTop={7} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
