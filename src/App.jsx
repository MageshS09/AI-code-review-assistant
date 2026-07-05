import { useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { LANGUAGES, getLanguageExtension, SAMPLE_CODE } from './languages'
import FindingsList from './FindingsList'
import SeverityChart from './SeverityChart'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function scoreColor(score) {
  if (score >= 9) return 'text-emerald-400'
  if (score >= 7) return 'text-lime-400'
  if (score >= 4) return 'text-amber-400'
  return 'text-red-400'
}

export default function App() {
  const [language, setLanguage] = useState('python')
  const [code, setCode] = useState(SAMPLE_CODE.python)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const handleLanguageChange = (nextLanguage) => {
    setLanguage(nextLanguage)
    setResult(null)
    setError('')
    if (!code.trim() || Object.values(SAMPLE_CODE).includes(code)) {
      setCode(SAMPLE_CODE[nextLanguage])
    }
  }

  const handleSubmit = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const response = await fetch(`${API_BASE}/api/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language }),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.error || 'Review request failed.')
      }
      setResult(data)
    } catch (err) {
      setError(err.message || 'Something went wrong while contacting the review API.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-lg font-semibold">AI Code Review Assistant</h1>
        <p className="text-sm text-slate-400">Static analysis for bugs, quality, security, and complexity.</p>
      </header>

      <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6 p-6 lg:grid-cols-2">
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <select
              value={language}
              onChange={(e) => handleLanguageChange(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-100"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </select>
            <button
              onClick={handleSubmit}
              disabled={loading || !code.trim()}
              className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? 'Reviewing…' : 'Review code'}
            </button>
          </div>

          <div className="overflow-hidden rounded-md border border-slate-800">
            <CodeMirror
              value={code}
              height="480px"
              theme="dark"
              extensions={[getLanguageExtension(language)]}
              onChange={(value) => setCode(value)}
            />
          </div>

          {error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
          )}
        </section>

        <section className="flex flex-col gap-4">
          {!result && !loading && (
            <div className="flex h-full min-h-[300px] items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-500">
              Submit code to see the review results here.
            </div>
          )}

          {loading && (
            <div className="flex h-full min-h-[300px] items-center justify-center rounded-md border border-slate-800 text-sm text-slate-500">
              Analyzing…
            </div>
          )}

          {result && (
            <>
              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-500">Score</p>
                    <p className={`text-3xl font-bold ${scoreColor(result.score)}`}>{result.score}/10</p>
                  </div>
                  <div className="text-right text-sm text-slate-300">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Complexity</p>
                    <p>Time {result.complexity.time} · Space {result.complexity.space}</p>
                  </div>
                </div>
                <p className="mt-3 text-sm text-slate-300">{result.verdict}</p>
                <p className="mt-1 text-xs text-slate-500">{result.complexity.explanation}</p>
              </div>

              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
                <h3 className="mb-3 text-sm font-semibold text-slate-200">Findings by severity</h3>
                <SeverityChart bugs={result.bugs} quality={result.quality} security={result.security} />
              </div>

              <div className="grid grid-cols-1 gap-4 rounded-md border border-slate-800 bg-slate-900/40 p-4 sm:grid-cols-3">
                <FindingsList title="Bugs" items={result.bugs} />
                <FindingsList title="Quality" items={result.quality} />
                <FindingsList title="Security" items={result.security} />
              </div>

              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-200">Refactored code</h3>
                <div className="overflow-hidden rounded-md border border-slate-800">
                  <CodeMirror
                    value={result.refactored_code}
                    height="320px"
                    theme="dark"
                    editable={false}
                    extensions={[getLanguageExtension(language)]}
                  />
                </div>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  )
}
