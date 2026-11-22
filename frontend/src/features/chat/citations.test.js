// Unit tests for toCitation: the backend's citation -> what the source buttons and panel show.
import { describe, expect, it } from 'vitest'
import { toCitation } from './citations'

// A small "factory": a valid citation with sensible defaults; each test overrides only what it is about.
const raw = (overrides = {}) => ({ marker: '[1]', document_id: 7, source_name: 'policy.pdf', snippet: 'Employees get 25 days.', ...overrides })

describe('toCitation', () => {
  it('turns the marker into a number and keeps the basics', () => {
    expect(toCitation(raw({ marker: '[12]' }))).toMatchObject({ n: 12, documentId: 7, filename: 'policy.pdf', snippet: 'Employees get 25 days.' })
  })

  it('a PDF page', () => {
    expect(toCitation(raw({ page_number: 3 }))).toMatchObject({ location: 'Page 3', shortLocation: 'p.3' })
  })

  it('a slide', () => {
    expect(toCitation(raw({ slide_number: 4 }))).toMatchObject({ location: 'Slide 4', shortLocation: 'slide 4' })
  })

  it('a range of spreadsheet rows', () => {
    const c = toCitation(raw({ sheet_name: 'Budget', row_start: 2, row_end: 9 }))
    expect(c).toMatchObject({ location: 'Sheet Budget, rows 2-9', shortLocation: 'rows 2-9' })
  })

  it('a single row is not written as a range', () => {
    expect(toCitation(raw({ sheet_name: 'Budget', row_start: 5, row_end: 5 })).location).toBe('Sheet Budget, rows 5')
  })

  it('a section heading when there is no page', () => {
    expect(toCitation(raw({ section_title: 'Time off' }))).toMatchObject({ location: 'Time off', shortLocation: null })
  })

  it('falls back when name, location and snippet are missing', () => {
    const c = toCitation({ marker: '[2]', document_id: 1, source_name: null, snippet: null })
    expect(c).toEqual({
      n: 2, documentId: 1, filename: 'Document', location: null, shortLocation: null, snippet: '',
      filePath: null, language: null, startLine: null, endLine: null, isCode: false, // CODEBASE-FEATURE
    })
  })

  // CODEBASE-FEATURE (Stage 3): source code citations
  describe('source code', () => {
    const code = (overrides = {}) =>
      raw({ source_name: 'app.zip', file_path: 'auth/jwt.py', language: 'python', start_line: 40, end_line: 72, snippet: 'def verify():\n    pass', ...overrides })

    it('names the file path, the lines and the language', () => {
      expect(toCitation(code())).toMatchObject({
        filename: 'auth/jwt.py', filePath: 'auth/jwt.py', language: 'python', startLine: 40, endLine: 72, isCode: true,
        location: 'Lines 40-72', shortLocation: 'lines 40-72',
      })
    })

    it('keeps the snippet exactly as sent (indentation and newlines)', () => {
      expect(toCitation(code()).snippet).toBe('def verify():\n    pass')
    })

    it('a single line is not written as a range', () => {
      expect(toCitation(code({ start_line: 5, end_line: 5 }))).toMatchObject({ location: 'Line 5', shortLocation: 'line 5' })
    })

    it('a code file with no line numbers (ingested before they existed) still shows its path', () => {
      const c = toCitation(code({ start_line: null, end_line: null }))
      expect(c).toMatchObject({ filename: 'auth/jwt.py', isCode: true, location: null, shortLocation: null })
    })

    it('a PDF citation is unchanged and is not code', () => {
      expect(toCitation(raw({ page_number: 3 }))).toMatchObject({ filename: 'policy.pdf', isCode: false, location: 'Page 3', filePath: null })
    })

    it('an old saved citation without any of the new keys still works', () => {
      const old = { marker: '[1]', document_id: 2, source_name: 'old.pdf', page_number: 1, snippet: 'x' }
      expect(toCitation(old)).toMatchObject({ filename: 'old.pdf', isCode: false, startLine: null })
    })
  })
})
