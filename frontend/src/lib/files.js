// What the backend can read (backend/app/services/document.py) and how files are shown.

// CODEBASE-FEATURE (Stage 4): what a chat accepts depends on its MODE, like on the backend (services/document.py):
//   'docs' chat: documents only.   'code' chat: source code (policy.py TIER1_CODE) plus Markdown and text (a README).
export const DOCUMENT_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.xlsx', '.csv', '.txt', '.md', '.markdown', '.html', '.htm']
export const CODE_EXTENSIONS = ['.py', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.java', '.c', '.h', '.cpp', '.hpp', '.cc', '.cxx']
// (Stage 11) a project .zip is accepted in a Codebase chat; the backend unpacks it (see backend zip_loader.py)
const CODE_CHAT_EXTENSIONS = [...CODE_EXTENSIONS, '.md', '.markdown', '.txt', '.zip']

export function acceptedExtensionsFor(mode = 'docs') {
  return mode === 'code' ? CODE_CHAT_EXTENSIONS : DOCUMENT_EXTENSIONS
}

// the value of the file picker's `accept` attribute
export function acceptAttributeFor(mode = 'docs') {
  return acceptedExtensionsFor(mode).join(',')
}
export const MAX_FILE_BYTES = 20 * 1024 * 1024 // the backend refuses anything larger (413)

export function extensionOf(name = '') {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? '' : name.slice(dot).toLowerCase()
}

// A reason to refuse the file before uploading it, or null if it looks fine. (The backend checks again.)
export function validateFile(file, mode = 'docs') {
  const ext = extensionOf(file.name)
  if (!acceptedExtensionsFor(mode).includes(ext)) {
    if (mode === 'code' && DOCUMENT_EXTENSIONS.includes(ext)) {
      return 'This is a Codebase chat: add source code (or Markdown or text), not documents. Start a Documents chat for those.'
    }
    if (mode !== 'code' && ext === '.zip') {
      return 'This file type is not supported here: a project zip goes in a Codebase chat. Start a new chat and choose Codebase.'
    }
    if (mode !== 'code' && CODE_EXTENSIONS.includes(ext)) {
      return 'Source code goes in a Codebase chat. Start a new chat and choose Codebase.'
    }
    return mode === 'code'
      ? 'This file type is not supported in a Codebase chat. Use source code (.py, .js, .ts, .java, .c, .cpp), Markdown, text or a project .zip.'
      : 'This file type is not supported. Use PDF, Word, PowerPoint, Excel, CSV, text, Markdown or HTML.'
  }
  if (file.size > MAX_FILE_BYTES) return 'This file is larger than 20 MB.'
  if (file.size === 0) return 'This file is empty.'
  return null
}

// "leave_policy.pdf" -> "PDF"
const LABELS = { '.markdown': 'MD', '.htm': 'HTML' }
export function fileTypeLabel(name) {
  const ext = extensionOf(name)
  return LABELS[ext] ?? (ext.slice(1).toUpperCase() || 'FILE')
}

// The backend sends UTC times WITHOUT a zone ("2026-11-07T19:49:01"); a browser would read that as local time.
export function parseServerDate(iso) {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
}

// "Today 14:05", "Yesterday 09:12", "3 Nov", "3 Nov 2025" (in the viewer's own time zone)
export function formatDate(iso) {
  const date = parseServerDate(iso)
  const now = new Date()
  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  if (date >= startOfToday) return `Today ${time}`
  if (date >= new Date(startOfToday - 86400000)) return `Yesterday ${time}`
  const sameYear = date.getFullYear() === now.getFullYear()
  return date.toLocaleDateString([], { day: 'numeric', month: 'short', ...(sameYear ? {} : { year: 'numeric' }) })
}

export const IN_PROGRESS = new Set(['pending', 'processing'])
