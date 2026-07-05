const SEVERITY_BADGE = {
  high: 'bg-red-500/15 text-red-400 ring-1 ring-red-500/30',
  medium: 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30',
  low: 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30',
}

export default function FindingsList({ title, items }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-200">
        {title} <span className="font-normal text-slate-500">({items.length})</span>
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">No issues found.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li key={i} className="flex items-start gap-2 rounded-md bg-slate-900/60 p-2.5 text-sm">
              <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${SEVERITY_BADGE[item.severity] || SEVERITY_BADGE.low}`}>
                {item.severity}
              </span>
              <span className="text-slate-300">
                <span className="mr-1 font-mono text-xs text-slate-500">L{item.line}</span>
                {item.description}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
