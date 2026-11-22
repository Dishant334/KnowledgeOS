// CODEBASE-FEATURE (Stage 3): the source panel for documents (unchanged) and for source code.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import CitationPanel from './CitationPanel'
import { toCitation } from './citations'

const codeSnippet = 'def verify(token):\n    if not token:\n        return None\n    return decode(token)'

const codeCitation = (snippet = codeSnippet) =>
  toCitation({ marker: '[1]', document_id: 5, source_name: 'app.zip', file_path: 'auth/jwt.py', language: 'python', start_line: 40, end_line: 43, snippet })

const pdfCitation = () => toCitation({ marker: '[2]', document_id: 6, source_name: 'policy.pdf', page_number: 3, snippet: 'Employees get 25 days.' })

const renderPanel = (citation, extra = {}) =>
  render(<CitationPanel citation={citation} others={[]} onClose={() => {}} onSwitch={() => {}} {...extra} />)

describe('CitationPanel with source code', () => {
  it('shows the file path, the language and the lines', () => {
    renderPanel(codeCitation())
    expect(screen.getByRole('heading', { name: 'auth/jwt.py' })).toBeInTheDocument()
    expect(screen.getByText('python · Lines 40-43')).toBeInTheDocument()
  })

  it('shows the code in a monospace block with its indentation kept', () => {
    const { container } = renderPanel(codeCitation())
    const pre = container.querySelector('pre')
    expect(pre).not.toBeNull()
    expect(pre.textContent).toBe(codeSnippet) // newlines and the 8-space indent are still there
    expect(pre.className).toMatch(/font-mono/)
    expect(pre.className).not.toMatch(/whitespace-normal/)
  })

  it('shows code that looks like HTML as plain text, never as markup', () => {
    const hostile = '<img src=x onerror=alert(1)>\n<script>alert(2)</script>'
    const { container } = renderPanel(codeCitation(hostile))
    expect(container.querySelector('pre').textContent).toBe(hostile)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
  })

  it('still says so when there is no snippet', () => {
    renderPanel(codeCitation(''))
    expect(screen.getByText(/not available/i)).toBeInTheDocument()
  })

  it('a code file without line numbers shows just the language', () => {
    renderPanel(toCitation({ marker: '[1]', document_id: 5, source_name: 'a.py', file_path: 'a.py', language: 'python', snippet: 'x = 1' }))
    expect(screen.getByText('python')).toBeInTheDocument()
  })
})

describe('CitationPanel with a document', () => {
  it('is unchanged: page location and a quote block, no code block', () => {
    const { container } = renderPanel(pdfCitation())
    expect(screen.getByRole('heading', { name: 'policy.pdf' })).toBeInTheDocument()
    expect(screen.getByText('Page 3')).toBeInTheDocument()
    expect(container.querySelector('blockquote')).toHaveTextContent('Employees get 25 days.')
    expect(container.querySelector('pre')).toBeNull()
  })
})

describe('CitationPanel behaviour', () => {
  it('closes with the X button and with Escape', async () => {
    const onClose = vi.fn()
    renderPanel(codeCitation(), { onClose })
    await userEvent.click(screen.getByRole('button', { name: 'Close source' }))
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
