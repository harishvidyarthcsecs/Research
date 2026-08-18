import { useMemo, useState } from 'react'
import { useDebounce } from './hooks/useDebounce'
import { useDarkMode } from './hooks/useDarkMode'
import { useFacets, useJournalSearch } from './hooks/useJournals'
import { Navbar } from './components/Navbar'
import { SearchBar } from './components/SearchBar'
import { FilterPanel } from './components/FilterPanel'
import { JournalCard } from './components/JournalCard'
import { SkeletonCard } from './components/SkeletonCard'
import { EmptyState } from './components/EmptyState'
import { ErrorState } from './components/ErrorState'
import { Pagination } from './components/Pagination'
import { JournalDetailModal } from './components/JournalDetailModal'
import type { JournalFilters } from './types/journal'

const DEFAULT_FILTERS: JournalFilters = {
  search: '',
  publisher: '',
  quartile: '',
  openAccess: false,
  annaUnivCfr: false,
  apcMax: '',
  sort: 'title',
  page: 1,
  pageSize: 20,
}

function App() {
  const [isDark, toggleDark] = useDarkMode()
  const [filters, setFilters] = useState<JournalFilters>(DEFAULT_FILTERS)
  const [selectedIssn, setSelectedIssn] = useState<string | null>(null)

  const debouncedSearch = useDebounce(filters.search, 350)
  const queryFilters = useMemo(
    () => ({ ...filters, search: debouncedSearch }),
    [filters, debouncedSearch],
  )

  const { data, isLoading, isError, error, refetch } = useJournalSearch(queryFilters)
  const { data: facets } = useFacets()

  const updateFilters = (patch: Partial<JournalFilters>) => {
    setFilters((prev) => ({ ...prev, ...patch, page: patch.page ?? 1 }))
  }

  const resetFilters = () => setFilters(DEFAULT_FILTERS)

  const results = data?.results ?? []
  const total = data?.total ?? 0

  return (
    <div className="min-h-screen">
      <Navbar isDark={isDark} onToggleDark={toggleDark} />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
          <SearchBar value={filters.search} onChange={(value) => updateFilters({ search: value })} />
        </div>

        <div className="mb-6">
          <FilterPanel
            filters={filters}
            publishers={facets?.publishers ?? []}
            onChange={updateFilters}
            onReset={resetFilters}
          />
        </div>

        {!isLoading && !isError && (
          <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
            {total.toLocaleString()} journal{total === 1 ? '' : 's'} found
          </p>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {isLoading &&
            Array.from({ length: filters.pageSize }).map((_, index) => <SkeletonCard key={index} />)}

          {isError && (
            <ErrorState
              message={error instanceof Error ? error.message : 'Something went wrong.'}
              onRetry={() => refetch()}
            />
          )}

          {!isLoading && !isError && results.length === 0 && <EmptyState onReset={resetFilters} />}

          {!isLoading &&
            !isError &&
            results.map((journal) => (
              <JournalCard key={journal.issn} journal={journal} onSelect={setSelectedIssn} />
            ))}
        </div>

        {!isLoading && !isError && (
          <Pagination
            page={filters.page}
            pageSize={filters.pageSize}
            total={total}
            onPageChange={(page) => setFilters((prev) => ({ ...prev, page }))}
          />
        )}
      </main>

      <JournalDetailModal issn={selectedIssn} onClose={() => setSelectedIssn(null)} />
    </div>
  )
}

export default App
