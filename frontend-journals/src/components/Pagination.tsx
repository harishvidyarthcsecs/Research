interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}

export function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (totalPages <= 1) return null

  const rangeStart = (page - 1) * pageSize + 1
  const rangeEnd = Math.min(total, page * pageSize)

  return (
    <div className="mt-8 flex flex-col items-center justify-between gap-3 sm:flex-row">
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        Showing <span className="font-medium text-neutral-700 dark:text-neutral-200">{rangeStart}–{rangeEnd}</span> of{' '}
        <span className="font-medium text-neutral-700 dark:text-neutral-200">{total.toLocaleString()}</span> journals
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn-ghost px-3 py-2"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          ← Prev
        </button>
        <span className="px-2 text-sm text-neutral-600 dark:text-neutral-300">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          className="btn-ghost px-3 py-2"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next →
        </button>
      </div>
    </div>
  )
}
