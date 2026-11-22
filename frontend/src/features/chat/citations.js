// The backend's citation -> what the chat shows.
// Backend: { marker: "[1]", document_id, source_name, page_number, slide_number, section_title, sheet_name,
//            row_start, row_end, snippet,
//            file_path, start_line, end_line, language }   <- source code only (all null for documents)

export function toCitation(raw) {
  return {
    n: Number.parseInt(String(raw.marker).replace(/\D/g, ''), 10),
    documentId: raw.document_id,
    // CODEBASE-FEATURE: for code the path is the title (inside a zip source_name is the zip, file_path the file)
    filename: raw.file_path || raw.source_name || 'Document',
    filePath: raw.file_path || null,
    language: raw.language || null,
    startLine: raw.start_line || null,
    endLine: raw.end_line || null,
    isCode: Boolean(raw.language || raw.file_path),
    location: locationOf(raw),
    shortLocation: shortLocationOf(raw),
    snippet: raw.snippet || '',
  }
}

// "Page 3", "Slide 4", "Sheet Budget, rows 2-9", "Section: Time off", or null
// CODEBASE-FEATURE: "Lines 40-72" / "Line 5" (shortForm: "lines 40-72" / "line 5"), or null without line numbers
function linesOf(raw, shortForm = false) {
  if (!raw.start_line) return null
  const word = shortForm ? 'line' : 'Line'
  return raw.end_line && raw.end_line !== raw.start_line
    ? `${word}s ${raw.start_line}-${raw.end_line}`
    : `${word} ${raw.start_line}`
}

function locationOf(raw) {
  if (raw.file_path || raw.language) return linesOf(raw)
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
  if (raw.file_path || raw.language) return linesOf(raw, true)
  if (raw.page_number) return `p.${raw.page_number}`
  if (raw.slide_number) return `slide ${raw.slide_number}`
  if (raw.row_start) return `rows ${raw.row_start}${raw.row_end && raw.row_end !== raw.row_start ? `-${raw.row_end}` : ''}`
  return null
}
