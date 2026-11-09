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
    expect(c).toEqual({ n: 2, documentId: 1, filename: 'Document', location: null, shortLocation: null, snippet: '' })
  })
})
