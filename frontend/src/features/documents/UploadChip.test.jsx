// Component tests for UploadChip: one file above the question box and what is happening to it.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import UploadChip from './UploadChip'

// The chip is an <li>, so render it inside a <ul> like the real list does.
const renderChip = (item, onRemove = () => {}) =>
  render(
    <ul>
      <UploadChip item={{ key: 'k1', name: 'policy.pdf', ...item }} onRemove={onRemove} />
    </ul>,
  )

describe('UploadChip', () => {
  it('shows upload progress as a percentage', () => {
    renderChip({ status: 'uploading', progress: 0.42 })
    expect(screen.getByText('Uploading 42%')).toBeInTheDocument()
  })

  it.each([
    ['pending', 'Waiting to be processed...'],
    ['processing', 'Reading the document...'],
  ])('status %s shows "%s"', (status, text) => {
    renderChip({ status, documentId: 3 })
    expect(screen.getByText(text)).toBeInTheDocument()
  })

  it('a failed document shows the reason from the backend', () => {
    renderChip({ status: 'failed', documentId: 3, failureReason: 'No readable text was found in this file.' })
    expect(screen.getByText('No readable text was found in this file.')).toBeInTheDocument()
  })

  it('a refused file shows why', () => {
    renderChip({ status: 'rejected', error: 'This file is larger than 20 MB.' })
    expect(screen.getByText('This file is larger than 20 MB.')).toBeInTheDocument()
  })

  it('a ready document is just its type and name, with no status line', () => {
    renderChip({ status: 'ready', documentId: 3 })
    expect(screen.getByText('PDF')).toBeInTheDocument()
    expect(screen.getByText('policy.pdf')).toBeInTheDocument()
    expect(screen.queryByText(/Ready to ask/)).not.toBeInTheDocument()
  })

  // The X button's label says what it will do, so the user (and a screen reader) knows before clicking.
  it.each([
    [{ status: 'ready', documentId: 3 }, 'Remove policy.pdf from your library'],
    [{ status: 'uploading', progress: 0.1 }, 'Cancel the upload of policy.pdf'],
    [{ status: 'rejected', error: 'nope' }, 'Dismiss policy.pdf'],
  ])('the X is labelled for what it does (%o)', (item, label) => {
    renderChip(item)
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
  })

  it('clicking the X reports the chip key', async () => {
    const onRemove = vi.fn()
    renderChip({ status: 'ready', documentId: 3 }, onRemove)
    await userEvent.setup().click(screen.getByRole('button', { name: /Remove policy.pdf/ }))
    expect(onRemove).toHaveBeenCalledWith('k1')
  })

  it('while deleting it shows a spinner instead of the X', () => {
    renderChip({ status: 'deleting', documentId: 3 })
    expect(screen.getByRole('status', { name: 'Removing' })).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
