import type { SortOption } from '../types/journal'

const OPTIONS: { value: SortOption; label: string }[] = [
  { value: 'title', label: 'Title (A–Z)' },
  { value: 'quartile', label: 'Quartile' },
  { value: 'apc', label: 'APC (low to high)' },
  { value: 'h_index', label: 'H-Index (high to low)' },
]

interface SortDropdownProps {
  value: SortOption
  onChange: (value: SortOption) => void
}

export function SortDropdown({ value, onChange }: SortDropdownProps) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value as SortOption)}
      className="select-glass"
      aria-label="Sort journals by"
    >
      {OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          Sort: {option.label}
        </option>
      ))}
    </select>
  )
}
