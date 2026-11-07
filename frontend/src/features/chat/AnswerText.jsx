import CitationChip from './CitationChip'

// An answer as plain TEXT (never HTML or markdown: the backend does not filter model output) with every [n] that
// matches a real source turned into a clickable chip. A [n] with no matching source stays as ordinary text.
export default function AnswerText({ text, citations = [], activeN, onOpen }) {
  const known = new Set(citations.map((c) => c.n))
  const parts = text.split(/(\[\d+\])/g)

  return (
    <p className="whitespace-pre-wrap leading-7 text-ink">
      {parts.map((part, i) => {
        const match = /^\[(\d+)\]$/.exec(part)
        const n = match ? Number(match[1]) : null
        if (n !== null && known.has(n)) {
          return <CitationChip key={i} n={n} active={activeN === n} onClick={() => onOpen(n)} />
        }
        return part
      })}
    </p>
  )
}
