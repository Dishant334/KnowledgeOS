// The backend's citation -> what the chat shows.
// Backend: { marker: "[1]", document_id, source_name, page_number, slide_number, section_title, sheet_name,
//            row_start, row_end, snippet }

export function toCitation(raw) {
  return {
    n: Number.parseInt(String(raw.marker).replace(/\D/g, ''), 10),
    documentId: raw.document_id,
    filename: raw.source_name || 'Document',
    location: locationOf(raw),
    shortLocation: shortLocationOf(raw),
    snippet: raw.snippet || '',
  }
}

// "Page 3", "Slide 4", "Sheet Budget, rows 2-9", "Section: Time off", or null
function locationOf(raw) {
  if (raw.page_number) return `Page ${raw.page_number}`
  if (raw.slide_number) return `Slide ${raw.slide_number}`
  if (raw.sheet_name) {
    const rows = raw.row_start ? `, rows ${raw.row_start}${raw.row_end && raw.row_end !== raw.row_start ? `-${raw.row_end}` : ''}` : ''
    return `Sheet ${raw.sheet_name}${rows}`
  }
  if (raw.section_title) return raw.section_title
  return null
}

// "p.3", "slide 4", "rows 2-9" (for the small source buttons under an answer)
function shortLocationOf(raw) {
  if (raw.page_number) return `p.${raw.page_number}`
  if (raw.slide_number) return `slide ${raw.slide_number}`
  if (raw.row_start) return `rows ${raw.row_start}${raw.row_end && raw.row_end !== raw.row_start ? `-${raw.row_end}` : ''}`
  return null
}
