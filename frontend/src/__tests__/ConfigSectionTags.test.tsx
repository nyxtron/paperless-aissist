import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { ConfigSectionTags } from '../components/ConfigSectionTags'
import { MODULAR_TAG_DEFAULTS } from '../constants'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

describe('ConfigSectionTags', () => {
  it('offers an input for every modular trigger tag', () => {
    // Guards against a trigger tag existing in the backend while the UI has no
    // field for it — ai-date was missing this way and could not be renamed.
    render(<ConfigSectionTags config={{}} onSave={vi.fn()} />)

    const placeholders = screen
      .getAllByRole('textbox')
      .map((input) => input.getAttribute('placeholder'))

    for (const tag of Object.values(MODULAR_TAG_DEFAULTS)) {
      expect(placeholders).toContain(tag)
    }
  })

  it('saves a renamed date tag', () => {
    const onSave = vi.fn()
    render(<ConfigSectionTags config={{}} onSave={onSave} />)

    const dateInput = screen
      .getAllByRole('textbox')
      .find((input) => input.getAttribute('placeholder') === 'ai-date')!

    fireEvent.change(dateInput, { target: { value: 'detect-date' } })

    expect(onSave).toHaveBeenCalledWith('modular_tag_date', 'detect-date')
  })
})
