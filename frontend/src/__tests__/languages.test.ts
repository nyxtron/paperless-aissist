import { describe, it, expect } from 'vitest'
import { LANGUAGES, orderLanguages, resources } from '../languages'
import en from '../locales/en.json'

describe('languages', () => {
  it('loads every locale file, English first', () => {
    expect(LANGUAGES).toEqual(['en', 'de'])
    expect(resources.en.translation).toEqual(en)
  })

  it('puts English first and the rest in alphabetical order', () => {
    expect(orderLanguages(['fr', 'de', 'en', 'cs'])).toEqual(['en', 'cs', 'de', 'fr'])
  })
})
