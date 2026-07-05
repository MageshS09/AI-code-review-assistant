const SEVERITY_ORDER = ['high', 'medium', 'low']

const SEVERITY_STYLE = {
  high: { color: '#e66767', label: 'High' },
  medium: { color: '#fab219', label: 'Medium' },
  low: { color: '#0ca30c', label: 'Low' },
}

const CATEGORIES = [
  { key: 'bugs', label: 'Bugs' },
  { key: 'quality', label: 'Quality' },
  { key: 'security', label: 'Security' },
]

function countBySeverity(items) {
  const counts = { high: 0, medium: 0, low: 0 }
  for (const item of items) {
    const severity = item.severity in counts ? item.severity : 'low'
    counts[severity] += 1
  }
  return counts
}

export default function SeverityChart({ bugs, quality, security }) {
  const dataByCategory = {
    bugs: countBySeverity(bugs),
    quality: countBySeverity(quality),
    security: countBySeverity(security),
  }

  const grandTotal = CATEGORIES.reduce((sum, { key }) => {
    const c = dataByCategory[key]
    return sum + c.high + c.medium + c.low
  }, 0)

  const totals = { high: 0, medium: 0, low: 0 }
  for (const { key } of CATEGORIES) {
    for (const sev of SEVERITY_ORDER) totals[sev] += dataByCategory[key][sev]
  }

  if (grandTotal === 0) {
    return <p className="text-sm text-slate-400">No findings to chart — nothing detected in any category.</p>
  }

  const maxTotal = Math.max(
    1,
    ...CATEGORIES.map(({ key }) => {
      const c = dataByCategory[key]
      return c.high + c.medium + c.low
    }),
  )

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        {CATEGORIES.map(({ key, label }) => {
          const counts = dataByCategory[key]
          const rowTotal = counts.high + counts.medium + counts.low
          return (
            <div key={key} className="flex items-center gap-3">
              <span className="w-16 shrink-0 text-xs font-medium text-slate-300">{label}</span>
              <div className="flex h-5 flex-1 gap-[2px]" role="img" aria-label={`${label}: ${rowTotal} findings`}>
                {rowTotal === 0 ? (
                  <div className="h-full w-full rounded bg-slate-800" />
                ) : (
                  SEVERITY_ORDER.filter((sev) => counts[sev] > 0).map((sev) => (
                    <div
                      key={sev}
                      className="h-full rounded-sm first:rounded-l last:rounded-r"
                      style={{
                        width: `${(counts[sev] / maxTotal) * 100}%`,
                        backgroundColor: SEVERITY_STYLE[sev].color,
                      }}
                      title={`${SEVERITY_STYLE[sev].label}: ${counts[sev]}`}
                    />
                  ))
                )}
              </div>
              <span className="w-6 shrink-0 text-right text-xs tabular-nums text-slate-400">{rowTotal}</span>
            </div>
          )
        })}
      </div>
      <div className="flex flex-wrap gap-4 border-t border-slate-800 pt-3 text-xs text-slate-300">
        {SEVERITY_ORDER.map((sev) => (
          <span key={sev} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: SEVERITY_STYLE[sev].color }} />
            {SEVERITY_STYLE[sev].label} ({totals[sev]})
          </span>
        ))}
      </div>
    </div>
  )
}
