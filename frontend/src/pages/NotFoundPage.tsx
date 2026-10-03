import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <main className="centered-page">
      <section className="error-panel">
        <p className="eyebrow">404 · Not found</p>
        <h1>This workspace does not exist yet.</h1>
        <p>Return to the application foundation.</p>
        <Link className="button-link" to="/">
          Return home
        </Link>
      </section>
    </main>
  )
}
