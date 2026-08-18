export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="glass-card page-enter col-span-full flex flex-col items-center gap-3 p-12 text-center">
      <span className="text-4xl">⚠️</span>
      <h3 className="text-lg font-semibold text-neutral-800 dark:text-neutral-100">Couldn't load journals</h3>
      <p className="max-w-sm text-sm text-neutral-500 dark:text-neutral-400">{message}</p>
      <button type="button" onClick={onRetry} className="btn-accent mt-1">
        Try again
      </button>
    </div>
  )
}
