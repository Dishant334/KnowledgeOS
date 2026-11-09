# KnowledgeOS frontend

This is the web app for [KnowledgeOS](../README.md): chat with your documents, see the passage behind every answer, and manage what the assistant remembers about you.

It's written in plain JavaScript with React 19, Vite 8, Tailwind CSS v4, React Router 7, axios and Clerk. There's no TypeScript, no state library and no markdown renderer, and all three are deliberate choices (see [Design rules](#design-rules)).

## Getting started

```bash
cp .env.example .env     # VITE_API_URL (default http://localhost:8000) and VITE_CLERK_PUBLISHABLE_KEY (pk_..., never the sk_ secret)
npm install
npm run dev              # http://localhost:5173
```

Port 5173 is pinned because it's the origin the backend allows by default (`CORS_ORIGINS`). Allow the same address in the Clerk dashboard. The backend must be running for anything past the sign-in page to work.

| Script | What it does |
|---|---|
| `npm run dev` | dev server with hot reload |
| `npm run build` | production build into `dist/` |
| `npm run preview` | serve the production build |
| `npm run lint` | ESLint |
| `npm test` | run all Vitest tests once |
| `npm run test:watch` | re-run the tests on every save |

## Structure

```
src/
  api/          client.js (axios + Clerk token), askStream.js (POST /ask/stream reader), errors.js (ApiError), one module per backend area
  auth/         sign-in / sign-up layout (sliding panel, artwork), Clerk wrapper and appearance, RequireAuth
  features/
    chat/       ChatLayout (the screen), sidebar, messages, citations, question box, rename dialog
    documents/  useUploads (queue, progress, polling) and the upload chips
    memory/     "What I remember about you" dialog
  components/   Button, Spinner, ErrorBanner, ErrorBoundary, ThemeLamp
  theme/        light / dark mode (saved in localStorage, else the system setting)
  lib/          constants (env), files (types, 20 MB limit, dates), ripple
  layout/ pages/ hooks/
  test/setup.js test environment (jest-dom matchers, cleanup, browser stand-ins)
```

Each test sits next to the file it tests (`*.test.js` / `*.test.jsx`).

## Design rules

- **Answers are plain text.** Model output and document snippets are rendered as text with `[n]` turned into citation chips. The app never uses `dangerouslySetInnerHTML` and never renders markdown, so HTML or a markdown image inside an answer stays harmless text. A test checks this.
- **Streaming uses `fetch`.** `POST /ask/stream` is read with a `ReadableStream` reader (`api/askStream.js`). The browser's `EventSource` can't send POST or an `Authorization` header, and axios can't stream in a browser. Stop uses an `AbortController`.
- **One token source.** The axios interceptor asks `window.Clerk.session.getToken()` before every request, so no React bridge can race the first call.
- **Every failure is an `ApiError`.** It carries a safe message, a `code` and, for a 429, `retryAfter`, so screens can say "Try again in 20 seconds."
- **Theme tokens only.** Colours come from the Pine & amber palette in `src/index.css` (`brand-*`, `paper`, `ink`, `highlight`, warm `stone-*` neutrals). Use `bg-surface` and `text-accent-ink` in app screens so dark mode works.
- **Motion is optional.** Animations only change `transform` and `opacity`, and they're switched off for `prefers-reduced-motion`.

## Tests

There are 119 tests (Vitest, jsdom, React Testing Library, user-event), and they run in under a second. They mock the API modules and Clerk, so no backend is needed.

| Kind | Examples |
|---|---|
| Pure functions | error mapping and `Retry-After`, citation labels (page, slide, rows), file validation, UTC dates |
| Stream parser | events split across network chunks, a broken event, a 429 before the stream, an error event, a cut-off stream, abort |
| Components | answer chips and the plain-text security check, upload chips, question box keys, rename and memory dialogs, sidebar day groups, error boundary |
| Hooks | upload queue, polling with fake timers, duplicate detection, a rename rolled back on error |
| Integration | the whole chat screen: ask, stream, open a source, move to `/chat/<id>`, Stop, 429 and Retry, opening a saved chat |
