import { motion } from 'framer-motion'
import type { JournalSummary } from '../types/journal'
import { Badge, ProvenanceChip, QuartileBadge } from './Badges'

interface JournalCardProps {
  journal: JournalSummary
  onSelect: (issn: string) => void
}

function formatApc(apcUsd: number | null): string {
  if (apcUsd === null || apcUsd === undefined) return 'No APC data'
  if (apcUsd === 0) return 'Free (no APC)'
  return `$${apcUsd.toLocaleString()} USD`
}

export function JournalCard({ journal, onSelect }: JournalCardProps) {
  return (
    <motion.div
      whileHover={{ y: -4 }}
      transition={{ type: 'spring', stiffness: 300, damping: 22 }}
      className="glass-card page-enter flex h-full flex-col justify-between p-5"
    >
      <div>
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <QuartileBadge quartile={journal.quartile} />
          {journal.in_doaj && <Badge tone="success">In DOAJ</Badge>}
          {journal.in_annauniv_cfr && <Badge tone="accent">Anna Univ CFR listed</Badge>}
          {journal.waiver_available && <Badge tone="neutral">Waiver available</Badge>}
        </div>

        <h3
          className="mb-2 line-clamp-2 text-base font-semibold leading-snug text-neutral-900 dark:text-neutral-50"
          title={journal.title}
        >
          {journal.title}
        </h3>

        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-neutral-500 dark:text-neutral-400">
          <div className="col-span-2 truncate">
            <dt className="inline font-medium text-neutral-400 dark:text-neutral-500">Publisher: </dt>
            <dd className="inline truncate">{journal.publisher ?? 'Unknown'}</dd>
          </div>
          <div className="truncate">
            <dt className="inline font-medium text-neutral-400 dark:text-neutral-500">ISSN: </dt>
            <dd className="inline">{journal.issn}</dd>
          </div>
          <div className="truncate">
            <dt className="inline font-medium text-neutral-400 dark:text-neutral-500">SJR: </dt>
            <dd className="inline">{journal.sjr ?? '—'}</dd>
          </div>
          <div className="truncate">
            <dt className="inline font-medium text-neutral-400 dark:text-neutral-500">H-Index: </dt>
            <dd className="inline">{journal.h_index ?? '—'}</dd>
          </div>
          <div className="truncate">
            <dt className="inline font-medium text-neutral-400 dark:text-neutral-500">APC: </dt>
            <dd className="inline">{formatApc(journal.apc_usd)}</dd>
          </div>
        </dl>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-neutral-200/60 pt-3 dark:border-neutral-800">
        <ProvenanceChip confidence={journal.apc_confidence} />
        <button
          type="button"
          onClick={() => onSelect(journal.issn)}
          className="text-sm font-semibold text-accent-600 transition-colors hover:text-accent-700 dark:text-accent-400 dark:hover:text-accent-300"
        >
          View details →
        </button>
      </div>
    </motion.div>
  )
}
