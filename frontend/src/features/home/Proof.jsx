import { useInView, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'

// ── Proof: what each upgrade did, in numbers ───────────────────────────────────────────────────────────────────────────
// Every number on this page is copied from the project's own README: the evaluation harness (backend/eval, 45 questions,
// local Qwen3 8B as generator and judge). Nothing is rounded up.
// Bars and counters start when the section scrolls into view; with "reduce motion" they simply appear.

// the three search set-ups the evaluation compared (the last one is what the app uses)
const CONFIGS = [
  { key: 'dense', label: 'Dense only', bar: 'bg-stone-300' },
  { key: 'hybrid', label: 'Hybrid (dense + BM25)', bar: 'bg-brand-400' },
  { key: 'rerank', label: 'Hybrid + rerank (used)', bar: 'bg-brand-700' },
]

// `values` are in the order of CONFIGS. `lower`: a smaller number is better (false refusals).
const METRICS = [
  { name: 'Answers correct', hint: 'of 45 questions', values: [0.74, 0.93, 0.93] },
  { name: 'All needed passages found', hint: 'Hit@5', values: [0.74, 0.93, 0.93] },
  { name: 'Right passage near the top', hint: 'MRR', values: [0.55, 0.78, 0.85] },
  { name: 'False refusals', hint: 'saying "I don\'t know" wrongly', values: [0.24, 0.07, 0.05], lower: true },
  { name: 'Cites an expected document', hint: 'citations', values: [0.74, 0.9, 0.93] },
  { name: 'Faithfulness', hint: 'RAGAS', values: [0.8, 0.75, 0.82] },
  { name: 'Context precision', hint: 'RAGAS', values: [0.52, 0.69, 0.74] },
]

const HEADLINES = [
  { from: 0.74, to: 0.93, decimals: 2, label: 'Answers correct', note: 'after adding BM25 to dense search' },
  { from: 0.55, to: 0.85, decimals: 2, label: 'Right passage near the top', note: 'MRR, after the reranker' },
  { from: 0.24, to: 0.05, decimals: 2, label: 'False refusals', note: 'down from almost 1 in 4' },
  { from: null, to: 3, decimals: 0, suffix: ' of 3', label: 'Out-of-scope questions refused', note: 'it never makes up an answer' },
]

const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))

// A number that counts up to `to` when it scrolls into view.
function CountUp({ to, decimals = 0, suffix = '', start }) {
  const reduced = useReducedMotion()
  const [value, setValue] = useState(reduced ? to : 0)
  useEffect(() => {
    if (!start || reduced) return
    let raf = 0
    const t0 = performance.now()
    const tick = (now) => {
      const t = clamp((now - t0) / 1300)
      setValue(to * (1 - Math.pow(1 - t, 3))) // eases out
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [start, reduced, to])
  const shown = start || reduced ? value : 0
  return (
    <>
      {shown.toFixed(decimals)}
      {suffix}
    </>
  )
}

export default function Proof() {
  const ref = useRef(null)
  const inView = useInView(ref, { once: true, margin: '0px 0px -15% 0px' })

  return (
    <section id="proof" ref={ref} className="scroll-mt-28 px-4 py-24 sm:px-6">
      <div className="mx-auto max-w-[1100px]">
        <div className="text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-ink">Proof</p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl lg:text-5xl">Measured, not claimed</h2>
          <p className="mx-auto mt-3 max-w-2xl text-stone-600">Every number below comes from the project's own evaluation run.</p>
        </div>

        {/* the four numbers that matter */}
        <ul className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {HEADLINES.map((h) => (
            <li key={h.label} className="rounded-2xl border border-stone-200 bg-surface p-5">
              <p className="h-5 text-sm text-stone-600">{h.from === null ? 'Ask what the files cannot answer' : <>from <span className="line-through decoration-stone-400">{h.from.toFixed(h.decimals)}</span></>}</p>
              <p className="mt-1 font-display text-5xl font-semibold tracking-tight text-accent-ink">
                <CountUp to={h.to} decimals={h.decimals} suffix={h.suffix} start={inView} />
              </p>
              <p className="mt-2 font-semibold text-ink">{h.label}</p>
              <p className="mt-0.5 text-sm text-stone-600">{h.note}</p>
            </li>
          ))}
        </ul>

        {/* the full comparison, bar by bar */}
        <div className="mt-6 rounded-2xl border border-stone-200 bg-surface p-5 sm:p-8">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="font-display text-2xl font-semibold text-ink">Each step up, on the same 45 questions</h3>
              <p className="mt-1 text-sm text-stone-600">13 documents, 121 chunks. Local Qwen3 8B is both the writer and the judge.</p>
            </div>
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-stone-600" aria-label="Legend">
              {CONFIGS.map((c) => (
                <li key={c.key} className="flex items-center gap-2">
                  <span className={`size-3 rounded-sm ${c.bar}`} aria-hidden="true" />
                  {c.label}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-6 divide-y divide-stone-200">
            {METRICS.map((m, row) => (
              <div key={m.name} className="grid gap-2 py-4 sm:grid-cols-[14rem_1fr] sm:items-center sm:gap-6">
                <div>
                  <p className="font-semibold text-ink">{m.name}</p>
                  <p className="text-xs text-stone-600">
                    {m.hint}
                    {m.lower && ' · lower is better'}
                  </p>
                </div>
                <div className="space-y-1.5">
                  {m.values.map((v, k) => (
                    <div key={CONFIGS[k].key} className="flex items-center gap-3">
                      <div className="h-3 flex-1 overflow-hidden rounded-full bg-stone-100">
                        <div
                          className={`h-full rounded-full ${CONFIGS[k].bar} motion-safe:transition-[width] motion-safe:duration-1000 motion-safe:ease-out`}
                          style={{ width: `${inView ? v * 100 : 0}%`, transitionDelay: `${row * 70 + k * 120}ms` }}
                        />
                      </div>
                      <span className={`w-10 text-right text-sm tabular-nums ${k === 2 ? 'font-semibold text-ink' : 'text-stone-600'}`}>{v.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-stone-600">RAGAS scores come from a small local judge on a 20-question sample: good for comparing the columns, not as absolute numbers.</p>
        </div>
      </div>
    </section>
  )
}
