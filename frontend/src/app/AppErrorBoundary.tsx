import {
  Component,
  type ErrorInfo,
  type PropsWithChildren,
  type ReactNode,
} from 'react'

type State = { hasError: boolean }

export class AppErrorBoundary extends Component<PropsWithChildren, State> {
  state: State = { hasError: false }
  static getDerivedStateFromError(): State {
    return { hasError: true }
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Application render failure', {
      error,
      componentStack: info.componentStack,
    })
  }
  render(): ReactNode {
    if (this.state.hasError)
      return (
        <main className="centered-page" role="alert">
          <section className="error-panel">
            <p className="eyebrow">Application error</p>
            <h1>The workspace could not be displayed.</h1>
            <p>
              Reload the page. If the problem continues, share the time of the
              error with IT.
            </p>
            <button type="button" onClick={() => window.location.reload()}>
              Reload application
            </button>
          </section>
        </main>
      )
    return this.props.children
  }
}
