// Every JSON file in locales/ is a language, named after its file: fr.json is "fr".
// Adding a language means adding its file; nothing else needs to know.
const files = import.meta.glob<{ default: Record<string, unknown> }>('./locales/*.json', {
  eager: true,
})

export const resources = Object.fromEntries(
  Object.entries(files).map(([path, module]) => [
    path.slice(path.lastIndexOf('/') + 1, -'.json'.length),
    { translation: module.default },
  ]),
)

// English is the fallback and comes first, the rest in alphabetical order.
export const orderLanguages = (codes: string[]): string[] =>
  [...codes].sort((a, b) => (a === 'en' ? -1 : b === 'en' ? 1 : a.localeCompare(b)))

export const LANGUAGES = orderLanguages(Object.keys(resources))
