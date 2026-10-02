import type { TFunction } from 'i18next'
import type { NamedCustomField } from '../api/types'

// Fields already on the document come along unchanged; empty ones say nothing.
export const filledFields = (fields: NamedCustomField[] | undefined): NamedCustomField[] =>
  (fields ?? []).filter(
    (f) => f.value !== null && f.value !== '' && !(Array.isArray(f.value) && f.value.length === 0),
  )

const formatValue = (value: NamedCustomField['value'], t: TFunction): string => {
  if (typeof value === 'boolean') return value ? t('common.yes') : t('common.no')
  return Array.isArray(value) ? value.join(', ') : String(value)
}

// Fields are set apart with a dot, since a link field's ids are already comma-separated.
export const formatFields = (fields: NamedCustomField[] | undefined, t: TFunction): string =>
  filledFields(fields)
    .map((f) => `${f.name}: ${formatValue(f.value, t)}`)
    .join(' · ')
