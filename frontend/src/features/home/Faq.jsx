import { useState } from 'react'

// ── FAQ: the questions people really ask about this project ──────────────────────────────────────────────────────────────
// Each answer repeats what the project's README and code say (limits, models, what is stored, what is not). If one of those
// changes (a limit, a model, a file type), change the matching answer here too.
// Several questions can be open at once; the answer slides open (a grid row growing from 0fr to 1fr, so no height has to be
// measured) and closed ones are `inert`, so keyboard and screen-reader users never land inside hidden text.

const FAQS = [
  {
    q: 'Which files can I upload?',
    a: 'PDF, Word, PowerPoint, Excel, CSV, Markdown and HTML, up to 20 MB each. Scanned pages are read with OCR (Tesseract), so a scan of a printed handbook works too. Images on their own are not accepted.',
  },
  {
    q: 'Do my documents leave my computer?',
    a: 'Not by default. The answers are written by a model that runs on your own machine (Qwen3 8B through Ollama), and the embedding and reranking models run locally too, so there is no paid API and your files stay yours. One optional exception: if you configure Gemini as a fallback, the text of the passages used for an answer is sent to Google when the local model fails. Leave that setting empty to stay fully local.',
  },
  {
    q: 'Can it make things up?',
    a: 'It is built not to. The model is told to answer only from the passages it is given and to cite each claim as [1], [2]… The numbers are matched back to real passages by code, so it cannot cite a source it was not given, and you can click any citation to read the exact passage. If your documents do not contain the answer, it says so. In the project\'s own evaluation it answered 93% of 45 questions correctly and refused all 3 questions that the documents could not answer.',
  },
  {
    q: 'Why does every chat have its own documents?',
    a: 'So projects never get mixed up. A document belongs to the chat it was added to, and a question searches only that chat\'s files. A chat with no documents cannot answer questions about them, so it asks you to add one first. Deleting a chat keeps its documents; deleting a document removes it everywhere.',
  },
  {
    q: 'What does "Remembers you" remember?',
    a: 'Short facts about you that help across chats, such as your role, your office or how you like answers written: up to 15 facts of 200 characters. They are used as background only, never as a source for an answer. You can see every fact, add your own, delete any of them, or forget everything. Passwords, secrets and anything that looks like an instruction are refused and never stored.',
  },
  {
    q: 'What if a document contains hidden instructions?',
    a: 'Document text is treated as untrusted data, not as instructions. It is placed only inside a separate context block, never in your question, and tests that assume a fully compromised model show it cannot invent citations or reach another user\'s files. Known gaps are written down openly in the README: the model\'s output is not filtered, so a markdown image link in an answer would not be removed by the API. The app itself is safe because it shows answers as plain text and never renders markdown or HTML.',
  },
  {
    q: 'Can other users see my files?',
    a: 'No. Every search is filtered by your user id and by the chat\'s documents, inside the search itself, so another user\'s passages can never come back. Sign-in is handled by Clerk, every route checks your token, and chats are addressed by random IDs that cannot be guessed or counted.',
  },
  {
    q: 'How fast is it?',
    a: 'The first question after the server starts takes about 30 seconds, because about 3 GB of models load once. After that, an answer starts to appear within a few seconds on a laptop, and the words stream in as they are written, so you can press Stop at any time. Uploads are processed in the background, and a question asked while a file is still being read waits for it by itself.',
  },
  {
    q: 'Are there limits on how much I can use it?',
    a: 'Yes, to keep one person from using everything: 10 questions a minute, 100 questions a day and 10 uploads an hour, per user. If you hit one, you see how many seconds to wait, and a refused question costs nothing.',
  },
  {
    q: 'What happens if I upload the same file twice?',
    a: 'It is recognised by its content (a hash), not by its name, so it is never stored or indexed twice. You see "Already in your library" and the existing copy is used.',
  },
  {
    q: 'Is it free, and how do I run it?',
    a: 'It needs no paid API: the models are open-source and run locally. Postgres, Qdrant and Redis start with one Docker Compose command, the backend is FastAPI and the frontend is React. The README has the setup step by step, and the whole backend runs against a test suite of 653 tests.',
  },
]

function Item({ q, a, open, onToggle, id }) {
  return (
    <div className="border-b border-stone-200 last:border-b-0">
      <h3>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={`${id}-panel`}
          id={`${id}-button`}
          className="flex w-full items-center justify-between gap-4 py-5 text-left transition-colors hover:text-accent-ink focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-700"
        >
          <span className="text-lg font-semibold text-ink">{q}</span>
          <span
            aria-hidden="true"
            className={`grid size-8 shrink-0 place-items-center rounded-full border border-stone-200 text-stone-600 motion-safe:transition-[transform,background-color,color] motion-safe:duration-300 ${open ? 'rotate-45 border-brand-700 bg-brand-700 text-white' : ''}`}
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </span>
        </button>
      </h3>
      {/* the answer: a grid row that grows from 0 to its own height */}
      <div
        id={`${id}-panel`}
        role="region"
        aria-labelledby={`${id}-button`}
        inert={!open}
        className={`grid motion-safe:transition-[grid-template-rows,opacity] motion-safe:duration-300 motion-safe:ease-out ${open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}`}
      >
        <div className="overflow-hidden">
          <p className="pb-5 pr-1 leading-relaxed sm:pr-12 text-stone-600">{a}</p>
        </div>
      </div>
    </div>
  )
}

export default function Faq() {
  const [openSet, setOpenSet] = useState(() => new Set([0])) // the first one starts open, so the section never looks empty

  const toggle = (i) =>
    setOpenSet((current) => {
      const next = new Set(current)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })

  return (
    <section id="faq" className="scroll-mt-28 px-4 py-24 sm:px-6">
      <div className="mx-auto max-w-[820px]">
        <div className="text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-ink">FAQ</p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl lg:text-5xl">Questions you might have</h2>
          <p className="mx-auto mt-3 max-w-xl text-stone-600">Straight answers about privacy, accuracy, limits and how it works.</p>
        </div>

        <div className="mt-10 rounded-2xl border border-stone-200 bg-surface px-5 sm:px-8">
          {FAQS.map((item, i) => (
            <Item key={item.q} id={`faq-${i}`} q={item.q} a={item.a} open={openSet.has(i)} onToggle={() => toggle(i)} />
          ))}
        </div>
      </div>
    </section>
  )
}
