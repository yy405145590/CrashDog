const ISO_DATETIME_WITHOUT_TIMEZONE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/

export function parseApiDateTime(value) {
  if (value instanceof Date) return value
  if (typeof value !== 'string') return new Date(value)

  const trimmed = value.trim()
  // SQLite drops tzinfo from UTC datetimes. Treat legacy offset-less API values
  // as UTC; values already carrying Z or an explicit offset remain unchanged.
  const normalized = ISO_DATETIME_WITHOUT_TIMEZONE.test(trimmed) ? `${trimmed}Z` : trimmed
  return new Date(normalized)
}

export function formatTime(value) {
  if (!value) return ''

  const date = parseApiDateTime(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('zh-CN', { hour12: false })
}
