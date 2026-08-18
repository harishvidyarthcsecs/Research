export function SkeletonCard() {
  return (
    <div className="glass-card flex h-full flex-col justify-between p-5">
      <div>
        <div className="mb-3 flex gap-1.5">
          <div className="skeleton h-5 w-10" />
          <div className="skeleton h-5 w-16" />
        </div>
        <div className="skeleton mb-2 h-4 w-full" />
        <div className="skeleton mb-4 h-4 w-3/4" />
        <div className="grid grid-cols-2 gap-2">
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-full" />
        </div>
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-neutral-200/60 pt-3 dark:border-neutral-800">
        <div className="skeleton h-4 w-20" />
        <div className="skeleton h-4 w-24" />
      </div>
    </div>
  )
}
