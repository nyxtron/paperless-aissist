import { describe, it, expect } from 'vitest'
import en from '../locales/en.json'
import de from '../locales/de.json'

const REVIEW = [
  'below_threshold',
  'low_mass',
  'final_none',
  'creation_off',
  'none_of_these',
  'named_existing',
  'no_name_prompt',
  'no_name',
  'untrusted_response',
  'claimed_existing_no_match',
  'implausible_name',
  'create_failed',
]
const FALLBACK = [
  'no_logprobs',
  'unsupported_parameter',
  'route_missing',
  'format_unsupported',
  'provider_unsupported',
  'url_missing',
  'model_missing',
  'prompt_inactive',
  'empty_list',
  'no_letters',
  'context_exceeded',
]
const OUTCOME = ['applied', 'created', 'would_create', 'review', 'fallback']

type Tree = Record<string, unknown>
const keys = (tree: Tree, prefix = ''): string[] =>
  Object.entries(tree).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? keys(v as Tree, `${prefix}${k}.`) : [`${prefix}${k}`],
  )

describe('decision locale keys', () => {
  it('cover every code in both languages', () => {
    for (const tree of [en as Tree, de as Tree]) {
      const all = new Set(keys(tree))
      for (const c of REVIEW) expect(all.has(`decision.reason.${c}`), c).toBe(true)
      for (const c of FALLBACK) expect(all.has(`decision.fallback.${c}`), c).toBe(true)
      for (const c of OUTCOME) expect(all.has(`decision.outcome.${c}`), c).toBe(true)
    }
  })

  it('have the same key set in en and de', () => {
    expect(keys(de as Tree).sort()).toEqual(keys(en as Tree).sort())
  })
})
