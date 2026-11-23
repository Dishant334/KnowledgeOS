// Unit tests for lib/files.js: which files may be uploaded, and how dates are shown.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MAX_FILE_BYTES, acceptAttributeFor, extensionOf, fileTypeLabel, formatDate, parseServerDate, validateFile } from './files'

// validateFile only reads .name and .size, so a plain object is enough (no need for a real File).
const file = (name, size = 1000) => ({ name, size })

describe('validateFile', () => {
  it.each(['report.pdf', 'notes.MD', 'deck.pptx', 'sheet.xlsx', 'data.csv', 'page.htm'])('accepts %s', (name) => {
    expect(validateFile(file(name))).toBeNull()
  })

  it.each(['photo.png', 'archive.zip', 'script.exe', 'no-extension'])('refuses %s', (name) => {
    expect(validateFile(file(name))).toMatch(/not supported/)
  })

  it('accepts exactly 20 MB and refuses one byte more', () => {
    expect(validateFile(file('big.pdf', MAX_FILE_BYTES))).toBeNull()
    expect(validateFile(file('big.pdf', MAX_FILE_BYTES + 1))).toBe('This file is larger than 20 MB.')
  })

  it('refuses an empty file', () => {
    expect(validateFile(file('empty.txt', 0))).toBe('This file is empty.')
  })
})

// CODEBASE-FEATURE (Stage 4): what a chat accepts depends on its mode (the backend enforces the same rule)
describe('validateFile by mode', () => {
  const CODE = ['main.py', 'app.js', 'App.jsx', 'util.mjs', 'x.cjs', 'api.ts', 'Page.tsx', 'Main.java', 'util.c', 'util.h', 'a.cpp', 'a.hpp', 'a.cc', 'a.cxx', 'SRC.PY']

  it.each(CODE)('a Codebase chat accepts the source file %s', (name) => {
    expect(validateFile(file(name), 'code')).toBeNull()
  })

  it.each(['README.md', 'guide.markdown', 'notes.txt'])('a Codebase chat also accepts %s', (name) => {
    expect(validateFile(file(name), 'code')).toBeNull()
  })

  it.each(['report.pdf', 'memo.docx', 'deck.pptx', 'sheet.xlsx', 'data.csv', 'page.html'])('a Codebase chat refuses the document %s', (name) => {
    expect(validateFile(file(name), 'code')).toMatch(/Codebase chat/)
  })

  it.each(['photo.png', 'archive.zip', 'no-extension'])('a Codebase chat refuses %s as not supported', (name) => {
    expect(validateFile(file(name), 'code')).toMatch(/not supported/)
  })

  it.each(CODE)('a Documents chat refuses the source file %s and points to Codebase', (name) => {
    expect(validateFile(file(name), 'docs')).toMatch(/Codebase/)
  })

  it('the mode defaults to documents', () => {
    expect(validateFile(file('report.pdf'))).toBeNull()
    expect(validateFile(file('main.py'))).toMatch(/Codebase/)
  })

  it('the size and empty-file rules apply in both modes', () => {
    expect(validateFile(file('big.py', MAX_FILE_BYTES + 1), 'code')).toBe('This file is larger than 20 MB.')
    expect(validateFile(file('empty.py', 0), 'code')).toBe('This file is empty.')
  })

  it('the file picker only offers what the mode accepts', () => {
    const docs = acceptAttributeFor('docs').split(',')
    const code = acceptAttributeFor('code').split(',')
    expect(docs).toContain('.pdf')
    expect(docs).not.toContain('.py')
    expect(code).toContain('.py')
    expect(code).toContain('.md')
    expect(code).not.toContain('.pdf')
  })
})

describe('file names', () => {
  it('finds the extension in lower case', () => {
    expect(extensionOf('Q3.Report.PDF')).toBe('.pdf')
    expect(extensionOf('README')).toBe('')
  })

  it('labels the type for the chip', () => {
    expect(fileTypeLabel('a.pdf')).toBe('PDF')
    expect(fileTypeLabel('a.markdown')).toBe('MD')
    expect(fileTypeLabel('a.htm')).toBe('HTML')
    expect(fileTypeLabel('README')).toBe('FILE')
    expect(fileTypeLabel('main.py')).toBe('PY') // CODEBASE-FEATURE
    expect(fileTypeLabel('Page.tsx')).toBe('TSX')
  })
})

describe('parseServerDate', () => {
  it('reads a time without a zone as UTC (the backend sends UTC)', () => {
    expect(parseServerDate('2026-11-07T19:49:01').toISOString()).toBe('2026-11-07T19:49:01.000Z')
  })

  it('keeps an explicit zone', () => {
    expect(parseServerDate('2026-11-07T19:49:01+02:00').toISOString()).toBe('2026-11-07T17:49:01.000Z')
    expect(parseServerDate('2026-11-07T19:49:01Z').toISOString()).toBe('2026-11-07T19:49:01.000Z')
  })
})

describe('formatDate', () => {
  // Fake timers freeze "now", so "Today" and "Yesterday" give the same result on any day the tests run.
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 10, 9, 15, 0)) // 9 Nov 2026, 15:00 local time (months count from 0)
  })
  afterEach(() => vi.useRealTimers())

  // local time -> the zone-less UTC text the backend would send for it
  const serverTime = (...parts) => new Date(...parts).toISOString().replace('Z', '')

  it('today', () => {
    expect(formatDate(serverTime(2026, 10, 9, 9, 5))).toMatch(/^Today /)
  })

  it('yesterday', () => {
    expect(formatDate(serverTime(2026, 10, 8, 23, 59))).toMatch(/^Yesterday /)
  })

  it('earlier this year shows day and month only', () => {
    const text = formatDate(serverTime(2026, 10, 3, 12, 0))
    expect(text).toMatch(/3/)
    expect(text).not.toMatch(/2026/)
  })

  it('a different year adds the year', () => {
    expect(formatDate(serverTime(2025, 10, 3, 12, 0))).toMatch(/2025/)
  })
})
