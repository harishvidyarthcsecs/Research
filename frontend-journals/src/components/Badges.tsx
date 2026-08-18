import type { ReactNode } from 'react'
import type { Confidence } from '../types/journal'

const QUARTILE_STYLES: Record<string, string> = {
  Q1: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400',
  Q2: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400',
  Q3: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',
  Q4: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400',
}

export function QuartileBadge({ quartile }: { quartile: string | null | undefined }) {
  if (!quartile) {
    return (
      <span className="inline-flex items-center rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-semibold text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
        No quartile
      </span>
    )
  }
  const style = QUARTILE_STYLES[quartile] ?? QUARTILE_STYLES.Q4
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${style}`}>
      {quartile}
    </span>
  )
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'accent' | 'success'
}) {
  const toneStyles: Record<string, string> = {
    neutral: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300',
    accent: 'bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300',
    success: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400',
  }
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${toneStyles[tone]}`}>
      {children}
    </span>
  )
}

const PROVENANCE_STYLES: Record<string, { label: string; className: string }> = {
  verified: {
    label: '✓ verified',
    className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400',
  },
  estimated: {
    label: '≈ estimated',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',
  },
  unknown: {
    label: '? unknown',
    className: 'bg-neutral-200 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300',
  },
  partial: {
    label: '◐ partial (login required)',
    className: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300',
  },
}

/** Small colored chip conveying data provenance/confidence, echoing the
 *  green/orange/grey convention used in templates/journal_fit.html. */
export function ProvenanceChip({
  confidence,
  partial = false,
}: {
  confidence: Confidence | null | undefined
  partial?: boolean
}) {
  const key = partial ? 'partial' : (confidence ?? 'unknown')
  const style = PROVENANCE_STYLES[key] ?? PROVENANCE_STYLES.unknown
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${style.className}`}
    >
      {style.label}
    </span>
  )
}
