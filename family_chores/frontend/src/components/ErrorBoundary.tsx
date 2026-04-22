import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * Last-resort boundary for render-time errors anywhere in the SPA. React
 * 18's default behaviour is to unmount the whole tree on an uncaught
 * render error — giving the kid tablet a permanent white screen. This
 * catches and shows a recover-from-this button that reloads the app.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Intentional: leave a breadcrumb in the console for debugging. We
    // don't POST to the backend because one of the failure modes here is
    // the backend being unreachable.
    console.error('[family-chores] render error:', error, info.componentStack)
  }

  private reset = (): void => {
    this.setState({ error: null })
  }

  private hardReset = (): void => {
    // Clear any persisted token state that might be driving the crash,
    // then reload. Kid-safe: no destructive writes to the DB.
    try {
      window.localStorage.removeItem('family-chores-parent')
    } catch {
      // ignore quota / disabled
    }
    window.location.reload()
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="min-h-screen grid place-items-center px-6 py-10">
        <div className="max-w-md w-full rounded-xl4 bg-white p-8 shadow-tile text-center">
          <div className="text-[clamp(3rem,6vw,5rem)]" aria-hidden>
            😳
          </div>
          <h1 className="mt-4 text-fluid-xl font-black text-brand-900">
            Oops — something broke.
          </h1>
          <p className="mt-3 text-fluid-base text-brand-700">
            Don't panic. Tap <strong>Try again</strong>. If it keeps
            happening, the Reset button below clears the saved parent
            session and reloads from scratch.
          </p>
          <pre className="mt-4 text-xs font-mono bg-brand-50 text-brand-900 rounded-xl p-3 max-h-40 overflow-auto text-left">
            {this.state.error.message}
          </pre>
          <div className="mt-6 flex gap-3 justify-center flex-wrap">
            <button
              type="button"
              onClick={this.reset}
              className="min-h-touch px-6 rounded-2xl bg-brand-600 text-white font-black text-fluid-base"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={this.hardReset}
              className="min-h-touch px-6 rounded-2xl bg-brand-50 text-brand-700 font-bold text-fluid-base"
            >
              Reset
            </button>
          </div>
        </div>
      </div>
    )
  }
}
