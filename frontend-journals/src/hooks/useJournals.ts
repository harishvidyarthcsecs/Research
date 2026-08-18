import { useQuery } from '@tanstack/react-query'
import { getFacets, getJournalDetail, searchJournals } from '../lib/api'
import type { JournalFilters } from '../types/journal'

export function useJournalSearch(filters: JournalFilters) {
  return useQuery({
    queryKey: ['journals', filters],
    queryFn: () => searchJournals(filters),
    placeholderData: (previous) => previous,
  })
}

export function useFacets() {
  return useQuery({
    queryKey: ['facets'],
    queryFn: getFacets,
    staleTime: 10 * 60 * 1000,
  })
}

export function useJournalDetail(issn: string | null) {
  return useQuery({
    queryKey: ['journal', issn],
    queryFn: () => getJournalDetail(issn as string),
    enabled: Boolean(issn),
  })
}
