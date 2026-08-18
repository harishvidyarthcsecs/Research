import type {
  FacetsResponse,
  JournalDetail,
  JournalFilters,
  JournalSearchResponse,
} from '../types/journal'

class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body?.error) message = body.error
    } catch {
      // ignore non-JSON error bodies
    }
    throw new ApiError(message, res.status)
  }
  return res.json() as Promise<T>
}

function buildSearchParams(filters: JournalFilters): string {
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  if (filters.publisher) params.set('publisher', filters.publisher)
  if (filters.quartile) params.set('quartile', filters.quartile)
  if (filters.openAccess) params.set('open_access', 'true')
  if (filters.annaUnivCfr) params.set('annauniv_cfr', 'true')
  if (filters.apcMax) params.set('apc_max', filters.apcMax)
  params.set('page', String(filters.page))
  params.set('page_size', String(filters.pageSize))
  params.set('sort', filters.sort)
  return params.toString()
}

export function searchJournals(filters: JournalFilters): Promise<JournalSearchResponse> {
  return request<JournalSearchResponse>(`/api/journals?${buildSearchParams(filters)}`)
}

export function getFacets(): Promise<FacetsResponse> {
  return request<FacetsResponse>('/api/journals/facets')
}

export function getJournalDetail(issn: string): Promise<JournalDetail> {
  return request<JournalDetail>(`/api/journals/${encodeURIComponent(issn)}`)
}

export { ApiError }
