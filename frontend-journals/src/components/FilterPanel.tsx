import { QuartileBadge } from './Badges'
import type { JournalFilters, SortOption } from '../types/journal'

const QUARTILES = ['Q1', 'Q2', 'Q3', 'Q4']

interface FilterPanelProps {
  filters: JournalFilters
  publishers: string[]
  onChange: (patch: Partial<JournalFilters>) => void
  onReset: () => void
}

interface Chip {
  key: string
  label: string
  onRemove: () => void
}

export function FilterPanel({ filters, publishers, onChange, onReset }: FilterPanelProps) {
  const chips: Chip[] = []
  if (filters.search) {
    chips.push({ key: 'search', label: `Search: "${filters.search}"`, onRemove: () => onChange({ search: '' }) })
  }
  if (filters.publisher) {
    chips.push({ key: 'publisher', label: filters.publisher, onRemove: () => onChange({ publisher: '' }) })
  }
  if (filters.quartile) {
    chips.push({ key: 'quartile', label: filters.quartile, onRemove: () => onChange({ quartile: '' }) })
  }
  if (filters.openAccess) {
    chips.push({ key: 'oa', label: 'Open Access only', onRemove: () => onChange({ openAccess: false }) })
  }
  if (filters.annaUnivCfr) {
    chips.push({ key: 'cfr', label: 'Anna Univ CFR list only', onRemove: () => onChange({ annaUnivCfr: false }) })
  }
  if (filters.apcMax) {
    chips.push({ key: 'apc', label: `APC ≤ $${filters.apcMax}`, onRemove: () => onChange({ apcMax: '' }) })
  }

  return (
    <div className="glass-panel sticky top-[68px] z-20 rounded-2xl p-4 sm:p-5">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-500 dark:text-neutral-400">
              Publisher
            </label>
            <select
              value={filters.publisher}
              onChange={(event) => onChange({ publisher: event.target.value, page: 1 })}
              className="select-glass w-full"
            >
              <option value="">All publishers</option>
              {publishers.map((publisher) => (
                <option key={publisher} value={publisher}>
                  {publisher}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-neutral-500 dark:text-neutral-400">
              Max APC (USD)
            </label>
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={filters.apcMax}
              onChange={(event) => onChange({ apcMax: event.target.value, page: 1 })}
              placeholder="No limit"
              className="input-glass"
            />
          </div>

          <div className="sm:col-span-2 lg:col-span-1">
            <label className="mb-1 block text-xs font-medium text-neutral-500 dark:text-neutral-400">
              Sort by
            </label>
            <select
              value={filters.sort}
              onChange={(event) => onChange({ sort: event.target.value as SortOption, page: 1 })}
              className="select-glass w-full"
            >
              <option value="title">Title (A–Z)</option>
              <option value="quartile">Quartile</option>
              <option value="apc">APC (low to high)</option>
              <option value="h_index">H-Index (high to low)</option>
            </select>
          </div>

          <div className="flex items-end">
            <label className="flex h-[42px] w-full cursor-pointer items-center gap-2 rounded-xl border border-neutral-200/80 bg-white/60 px-3 text-sm dark:border-neutral-700/80 dark:bg-neutral-900/50">
              <input
                type="checkbox"
                checked={filters.openAccess}
                onChange={(event) => onChange({ openAccess: event.target.checked, page: 1 })}
                className="h-4 w-4 accent-accent-500"
              />
              Open Access only
            </label>
          </div>

          <div className="flex items-end">
            <label className="flex h-[42px] w-full cursor-pointer items-center gap-2 rounded-xl border border-neutral-200/80 bg-white/60 px-3 text-sm dark:border-neutral-700/80 dark:bg-neutral-900/50">
              <input
                type="checkbox"
                checked={filters.annaUnivCfr}
                onChange={(event) => onChange({ annaUnivCfr: event.target.checked, page: 1 })}
                className="h-4 w-4 accent-accent-500"
              />
              Anna Univ CFR list only
            </label>
          </div>
        </div>

        <div>
          <span className="mb-1.5 block text-xs font-medium text-neutral-500 dark:text-neutral-400">
            Quartile
          </span>
          <div className="flex flex-wrap gap-2">
            {QUARTILES.map((q) => {
              const active = filters.quartile === q
              return (
                <button
                  key={q}
                  type="button"
                  onClick={() => onChange({ quartile: active ? '' : q, page: 1 })}
                  className={`flex items-center gap-1.5 rounded-full border px-1 py-1 pr-3 transition-colors ${
                    active
                      ? 'border-accent-400 bg-accent-50 dark:border-accent-500 dark:bg-accent-900/30'
                      : 'border-neutral-200 bg-white/50 hover:border-neutral-300 dark:border-neutral-700 dark:bg-neutral-900/40'
                  }`}
                >
                  <QuartileBadge quartile={q} />
                </button>
              )
            })}
          </div>
        </div>

        {chips.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-t border-neutral-200/60 pt-3 dark:border-neutral-800">
            {chips.map((chip) => (
              <button
                key={chip.key}
                type="button"
                onClick={chip.onRemove}
                className="inline-flex items-center gap-1.5 rounded-full bg-accent-100 px-3 py-1 text-xs font-medium text-accent-700 transition-colors hover:bg-accent-200 dark:bg-accent-900/40 dark:text-accent-300 dark:hover:bg-accent-900/60"
              >
                {chip.label}
                <span aria-hidden="true">✕</span>
              </button>
            ))}
            <button
              type="button"
              onClick={onReset}
              className="text-xs font-semibold text-neutral-500 underline-offset-2 hover:text-neutral-700 hover:underline dark:text-neutral-400 dark:hover:text-neutral-200"
            >
              Reset all
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
