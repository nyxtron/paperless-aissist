import type { TFunction } from 'i18next'

// Step names as the backend reports them; anything else is shown as it comes.
const STEP_NAMES = [
  'ocr',
  'ocr_fix',
  'date',
  'title',
  'correspondent',
  'document_type',
  'tags',
  'fields',
] as const

type StepName = (typeof STEP_NAMES)[number]

const isStepName = (name: string): name is StepName =>
  (STEP_NAMES as readonly string[]).includes(name)

export function stepLabel(t: TFunction, name: string): string {
  return isStepName(name) ? t(`processing.stepName.${name}`) : name
}
