// Stage 11: the browser's copy of the server's file policy must give the SAME answers. Both sides are tested against one
// list (backend/tests/policy_cases.json), generated from the server's own policy.classify().
import { describe, expect, it } from 'vitest'
import cases from '../../../backend/tests/policy_cases.json'
import { classifyPath } from './codePolicy'

describe('classifyPath', () => {
  it('has a meaningful shared list', () => {
    expect(cases.length).toBeGreaterThan(50)
    expect(cases.some((c) => c.accepted)).toBe(true)
    expect(cases.some((c) => !c.accepted)).toBe(true)
  })

  it.each(cases.map((c) => [JSON.stringify(c.path), c]))('%s gives the same answer as the server', (_, c) => {
    expect(classifyPath(c.path)).toEqual({ accepted: c.accepted, tier: c.tier, reason: c.reason })
  })
})
