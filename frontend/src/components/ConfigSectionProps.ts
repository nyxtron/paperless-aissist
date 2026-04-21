export interface ConfigSectionProps {
  config: Record<string, string>
  onSave: (key: string, value: string) => Promise<void>
  onTest?: (key: string) => Promise<boolean>
  secretsSet?: string[]
}
