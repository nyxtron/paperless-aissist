import type { TFunction } from 'i18next'

// Step names and results as the backend reports them; anything else is shown as it comes.
export const STEP_NAMES = [
  'ocr',
  'ocr_fix',
  'date',
  'title',
  'correspondent',
  'document_type',
  'tags',
  'fields',
] as const

export const STEP_STATUSES = ['completed', 'skipped', 'failed'] as const

type StepName = (typeof STEP_NAMES)[number]
type StepStatus = (typeof STEP_STATUSES)[number]

const isStepName = (name: string): name is StepName =>
  (STEP_NAMES as readonly string[]).includes(name)

const isStepStatus = (status: string): status is StepStatus =>
  (STEP_STATUSES as readonly string[]).includes(status)

export function stepLabel(t: TFunction, name: string): string {
  return isStepName(name) ? t(`processing.stepName.${name}`) : name
}

export function stepStatusLabel(t: TFunction, status: string): string {
  return isStepStatus(status) ? t(`processing.stepStatus.${status}`) : status
}
