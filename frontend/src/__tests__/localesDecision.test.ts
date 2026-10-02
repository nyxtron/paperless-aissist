import { describe, it, expect } from 'vitest'
import en from '../locales/en.json'
import { resources } from '../languages'
import { STEP_NAMES, STEP_STATUSES } from '../utils/stepLabels'

// Every language the app loads, so a new language is held to the same keys.
const LOCALES = Object.entries(resources).map(
  ([language, { translation }]) => [`${language}.json`, translation] as const,
)

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
  it('cover every code and step word in every language', () => {
    expect(LOCALES.map(([file]) => file)).toEqual(expect.arrayContaining(['de.json', 'en.json']))
    for (const [file, tree] of LOCALES) {
      const all = new Set(keys(tree as Tree))
      for (const c of REVIEW) expect(all.has(`decision.reason.${c}`), `${file} ${c}`).toBe(true)
      for (const c of FALLBACK) expect(all.has(`decision.fallback.${c}`), `${file} ${c}`).toBe(true)
      for (const c of OUTCOME) expect(all.has(`decision.outcome.${c}`), `${file} ${c}`).toBe(true)
      for (const c of STEP_NAMES)
        expect(all.has(`processing.stepName.${c}`), `${file} ${c}`).toBe(true)
      for (const c of STEP_STATUSES)
        expect(all.has(`processing.stepStatus.${c}`), `${file} ${c}`).toBe(true)
    }
  })

  it('have the same key set as English in every language', () => {
    for (const [file, tree] of LOCALES) {
      expect(keys(tree as Tree).sort(), file).toEqual(keys(en as Tree).sort())
    }
  })
})
