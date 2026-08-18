interface NavbarProps {
  isDark: boolean
  onToggleDark: () => void
}

export function Navbar({ isDark, onToggleDark }: NavbarProps) {
  return (
    <header className="glass-panel sticky top-0 z-30">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-2.5">
          <span className="text-2xl" aria-hidden="true">
            📚
          </span>
          <div>
            <h1 className="text-lg font-bold leading-none">
              <span className="gradient-text">Journal</span>{' '}
              <span className="text-neutral-900 dark:text-neutral-100">Database</span>
            </h1>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              SCImago · Scopus · DOAJ · Anna Univ CFR
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onToggleDark}
          aria-label="Toggle dark mode"
          className="btn-ghost h-10 w-10 rounded-full p-0 text-base"
        >
          {isDark ? '☀️' : '🌙'}
        </button>
      </div>
    </header>
  )
}
