export function EmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div className="glass-card page-enter col-span-full flex flex-col items-center gap-3 p-12 text-center">
      <span className="text-4xl">🔍</span>
      <h3 className="text-lg font-semibold text-neutral-800 dark:text-neutral-100">No journals found</h3>
      <p className="max-w-sm text-sm text-neutral-500 dark:text-neutral-400">
        Try widening your search, removing a filter, or raising the max APC.
      </p>
      <button type="button" onClick={onReset} className="btn-ghost mt-1">
        Reset all filters
      </button>
    </div>
  )
}
