export const fieldClass =
  'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
export const labelClass = 'block text-sm font-medium text-gray-700 mb-1'
export const hintClass = 'text-xs text-gray-500 mt-1'

export const sourceBadgeClass = (source: string) =>
  source === 'env'
    ? 'bg-blue-100 text-blue-700'
    : 'bg-amber-100 text-amber-700'
