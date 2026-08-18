import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useJournalDetail } from '../hooks/useJournals'
import { Badge, ProvenanceChip, QuartileBadge } from './Badges'
import type { RiskSeverity } from '../types/journal'

interface JournalDetailModalProps {
  issn: string | null
  onClose: () => void
}

const RISK_STYLES: Record<string, string> = {
  high: 'border-red-300 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400',
  medium:
    'border-orange-300 bg-orange-50 text-orange-700 dark:border-orange-500/30 dark:bg-orange-500/10 dark:text-orange-400',
  low: 'border-yellow-300 bg-yellow-50 text-yellow-700 dark:border-yellow-500/30 dark:bg-yellow-500/10 dark:text-yellow-400',
}

function riskStyle(severity: RiskSeverity): string {
  return RISK_STYLES[severity] ?? RISK_STYLES.low
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-neutral-200/60 pt-4 first:border-t-0 first:pt-0 dark:border-neutral-800">
      <h3 className="mb-2.5 text-sm font-semibold text-neutral-800 dark:text-neutral-100">{title}</h3>
      {children}
    </section>
  )
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-neutral-400 dark:text-neutral-500">{label}</dt>
      <dd className="text-sm text-neutral-800 dark:text-neutral-100">{value ?? '—'}</dd>
    </div>
  )
}

export function JournalDetailModal({ issn, onClose }: JournalDetailModalProps) {
  const { data, isLoading, isError } = useJournalDetail(issn)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    if (issn) {
      document.addEventListener('keydown', onKeyDown)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
  }, [issn, onClose])

  return (
    <AnimatePresence>
      {issn && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-neutral-900/50 p-4 py-10 backdrop-blur-sm sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 340, damping: 30 }}
            className="glass-card w-full max-w-2xl bg-white/95 p-6 dark:bg-neutral-950/95"
            onClick={(event) => event.stopPropagation()}
          >
            {isLoading && (
              <div className="space-y-3 py-8">
                <div className="skeleton h-6 w-2/3" />
                <div className="skeleton h-4 w-1/2" />
                <div className="skeleton h-32 w-full" />
              </div>
            )}

            {isError && (
              <div className="py-8 text-center">
                <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
                  Couldn't load details for this journal.
                </p>
                <button type="button" onClick={onClose} className="btn-ghost">
                  Close
                </button>
              </div>
            )}

            {data && (
              <div className="space-y-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="mb-2 flex flex-wrap items-center gap-1.5">
                      {data.scimago?.quartile && <QuartileBadge quartile={data.scimago.quartile} />}
                      {data.doaj?.in_doaj && <Badge tone="success">In DOAJ</Badge>}
                      {data.in_annauniv_cfr && <Badge tone="accent">Anna Univ CFR listed</Badge>}
                    </div>
                    <h2 className="text-xl font-bold leading-snug text-neutral-900 dark:text-neutral-50">
                      {data.title}
                    </h2>
                    <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
                      {data.publisher ?? 'Unknown publisher'} · {data.country ?? 'Unknown country'} · ISSN {data.issn}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={onClose}
                    aria-label="Close"
                    className="btn-ghost h-9 w-9 shrink-0 rounded-full p-0"
                  >
                    ✕
                  </button>
                </div>

                <Section title="SCImago">
                  {data.scimago ? (
                    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      <Field label="SJR" value={data.scimago.sjr} />
                      <Field label="Quartile" value={data.scimago.quartile} />
                      <Field label="H-Index" value={data.scimago.h_index} />
                      <Field label="Subject" value={data.scimago.subject_category} />
                      <Field label="Coverage" value={data.scimago.coverage} />
                      <Field
                        label="Source"
                        value={
                          data.scimago.source_url ? (
                            <a
                              href={data.scimago.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-accent-600 hover:underline dark:text-accent-400"
                            >
                              View source ↗
                            </a>
                          ) : null
                        }
                      />
                    </dl>
                  ) : (
                    <p className="text-sm text-neutral-400">No SCImago data available.</p>
                  )}
                </Section>

                <Section title="Scopus">
                  {data.scopus ? (
                    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      <Field label="CiteScore" value={data.scopus.citescore} />
                      <Field label="Percentile" value={data.scopus.percentile ? `${data.scopus.percentile}%` : null} />
                      <Field label="ASJC codes" value={data.scopus.asjc_codes} />
                      <Field label="Status" value={data.scopus.active_status} />
                    </dl>
                  ) : (
                    <p className="text-sm text-neutral-400">
                      Unavailable — Scopus data requires a Scopus/Elsevier account
                      (confirmed: scopus.com redirects to Elsevier's login, no public
                      source list exists). Not shown here rather than guessed.
                    </p>
                  )}
                </Section>

                <Section title="Master Journal List (MJL)">
                  {data.mjl ? (
                    <div>
                      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                        <Field label="JIF" value={data.mjl.jif} />
                        <Field label="Quartile" value={data.mjl.quartile} />
                        <Field label="Edition" value={data.mjl.edition} />
                      </dl>
                      {data.mjl.is_partial && (
                        <div className="mt-2">
                          <ProvenanceChip confidence="unknown" partial />
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-neutral-400">
                      Unavailable — Web of Science / MJL data requires a free
                      Clarivate account export (mjl.clarivate.com gates JIF/quartile
                      behind login). Not shown here rather than guessed.
                    </p>
                  )}
                </Section>

                <Section title="DOAJ">
                  {data.doaj ? (
                    <div className="space-y-2">
                      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                        <Field label="In DOAJ" value={data.doaj.in_doaj ? 'Yes' : 'No'} />
                        <Field label="Has APC" value={data.doaj.has_apc ? 'Yes' : 'No'} />
                        <Field
                          label="APC amount"
                          value={
                            data.doaj.apc_amount != null
                              ? `${data.doaj.apc_amount.toLocaleString()} ${data.doaj.apc_currency ?? ''}`.trim()
                              : null
                          }
                        />
                        <Field label="License" value={data.doaj.license_type} />
                        <Field
                          label="Last checked live"
                          value={data.doaj.live_checked_at ? new Date(data.doaj.live_checked_at).toLocaleDateString() : null}
                        />
                        <Field label="Diverged from CSV" value={data.doaj.diverged_from_csv ? 'Yes' : 'No'} />
                      </dl>
                      {data.doaj.waiver_policy_text && (
                        <p className="rounded-lg bg-neutral-100 p-3 text-xs text-neutral-600 dark:bg-neutral-900 dark:text-neutral-300">
                          {data.doaj.waiver_policy_text}{' '}
                          {data.doaj.waiver_policy_url && (
                            <a
                              href={data.doaj.waiver_policy_url}
                              target="_blank"
                              rel="noreferrer"
                              className="font-medium text-accent-600 hover:underline dark:text-accent-400"
                            >
                              Read policy ↗
                            </a>
                          )}
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-neutral-400">No DOAJ data available.</p>
                  )}
                </Section>

                <Section title="APC (consolidated)">
                  {data.apc_consolidated ? (
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-neutral-800 dark:text-neutral-100">
                          {data.apc_consolidated.apc_usd != null
                            ? `$${data.apc_consolidated.apc_usd.toLocaleString()} USD`
                            : 'No APC figure available'}
                        </span>
                        <ProvenanceChip confidence={data.apc_consolidated.confidence} />
                      </div>
                      <p className="text-xs text-neutral-400 dark:text-neutral-500">
                        Source: {data.apc_consolidated.source ?? 'unknown'}
                      </p>
                      {data.apc_consolidated.waiver_available && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                          <p className="mb-1 font-semibold">Waiver may be available — advisory only</p>
                          <p>
                            {data.apc_consolidated.waiver_notes ??
                              'Waiver eligibility varies by author, institution, and country. Always verify directly with the publisher at submission.'}
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-neutral-400">No consolidated APC data available.</p>
                  )}
                </Section>

                {data.publisher_apcs.length > 0 && (
                  <Section title="Publisher APC listings">
                    <ul className="space-y-2">
                      {data.publisher_apcs.map((item, index) => (
                        <li
                          key={`${item.publisher}-${index}`}
                          className="flex items-center justify-between rounded-lg bg-neutral-100 px-3 py-2 text-sm dark:bg-neutral-900"
                        >
                          <span>
                            <span className="font-medium capitalize text-neutral-800 dark:text-neutral-100">
                              {item.publisher}
                            </span>
                            {item.list_type && (
                              <span className="ml-2 text-xs text-neutral-500 dark:text-neutral-400">
                                ({item.list_type})
                              </span>
                            )}
                          </span>
                          <span className="flex items-center gap-2">
                            <span className="font-medium">
                              {item.apc_amount != null
                                ? `${item.apc_amount.toLocaleString()} ${item.currency ?? ''}`.trim()
                                : '—'}
                            </span>
                            {item.source_url && (
                              <a
                                href={item.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs text-accent-600 hover:underline dark:text-accent-400"
                              >
                                source ↗
                              </a>
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}

                {data.risk_flags.length > 0 && (
                  <Section title="Risk flags">
                    <ul className="space-y-2">
                      {data.risk_flags.map((flag, index) => (
                        <li
                          key={`${flag.type}-${index}`}
                          className={`rounded-lg border px-3 py-2 text-xs ${riskStyle(flag.severity)}`}
                        >
                          <p className="font-semibold uppercase tracking-wide">
                            {flag.severity} · {flag.type.replace(/_/g, ' ')}
                          </p>
                          <p className="mt-0.5">{flag.reason}</p>
                          <p className="mt-0.5 opacity-70">Source: {flag.source}</p>
                        </li>
                      ))}
                    </ul>
                  </Section>
                )}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
