// Types mirror the exact JSON shapes returned by src/blueprints/journals.py.
// Keep these in sync with that file if the API contract changes.

export type Quartile = 'Q1' | 'Q2' | 'Q3' | 'Q4'

export type Confidence = 'verified' | 'estimated' | 'unknown' | string

export type RiskSeverity = 'high' | 'medium' | 'low' | string

/** One row from GET /api/journals */
export interface JournalSummary {
  issn: string
  title: string
  publisher: string | null
  country: string | null
  quartile: Quartile | string | null
  quartile_source: 'verified' | 'unknown' | string
  sjr: number | null
  h_index: number | null
  subject_category: string | null
  in_doaj: boolean
  apc_usd: number | null
  apc_source: string
  apc_confidence: Confidence
  waiver_available: boolean | null
  in_annauniv_cfr: boolean
}

export interface JournalSearchResponse {
  total: number
  page: number
  page_size: number
  results: JournalSummary[]
}

export interface FacetsResponse {
  publishers: string[]
  quartiles: string[]
}

export interface ScimagoDetail {
  sjr: number | null
  quartile: Quartile | string | null
  h_index: number | null
  subject_category: string | null
  coverage: string | null
  source_url: string | null
  snapshot_date: string | null
}

export interface ScopusDetail {
  citescore: number | null
  percentile: number | null
  asjc_codes: string | null
  active_status: string | null
}

export interface MjlDetail {
  jif: number | null
  quartile: Quartile | string | null
  edition: string | null
  is_partial: boolean | null
}

export interface DoajDetail {
  in_doaj: boolean | null
  has_apc: boolean | null
  apc_amount: number | null
  apc_currency: string | null
  waiver_policy_text: string | null
  waiver_policy_url: string | null
  license_type: string | null
  live_checked_at: string | null
  diverged_from_csv: boolean | null
}

export interface ApcConsolidated {
  apc_usd: number | null
  source: string | null
  confidence: Confidence
  waiver_available: boolean | null
  waiver_notes: string | null
}

export interface PublisherApc {
  publisher: string | null
  list_type: string | null
  apc_amount: number | null
  currency: string | null
  source_url: string | null
}

export interface RiskFlag {
  type: string
  severity: RiskSeverity
  reason: string
  source: string
}

/** GET /api/journals/<issn> */
export interface JournalDetail {
  issn: string
  title: string
  publisher: string | null
  country: string | null
  scimago: ScimagoDetail | null
  scopus: ScopusDetail | null
  mjl: MjlDetail | null
  doaj: DoajDetail | null
  in_annauniv_cfr: boolean
  apc_consolidated: ApcConsolidated | null
  publisher_apcs: PublisherApc[]
  risk_flags: RiskFlag[]
}

export type SortOption = 'title' | 'quartile' | 'apc' | 'h_index'

export interface JournalFilters {
  search: string
  publisher: string
  quartile: string
  openAccess: boolean
  annaUnivCfr: boolean
  apcMax: string
  sort: SortOption
  page: number
  pageSize: number
}
