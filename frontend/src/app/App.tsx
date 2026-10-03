import { lazy, Suspense, type ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'
import { FoundationPage } from '../features/foundation/FoundationPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { LoginPage } from '../features/auth/LoginPage'
import { ProtectedRoute } from '../features/auth/ProtectedRoute'
import { AppShell } from '../features/foundation/AppShell'

const AccessPage = lazy(() =>
  import('../features/access/AccessPage').then((module) => ({
    default: module.AccessPage,
  })),
)
const DirectoryPage = lazy(() =>
  import('../features/directory/DirectoryPage').then((module) => ({
    default: module.DirectoryPage,
  })),
)
const TicketDetailPage = lazy(() =>
  import('../features/tickets/TicketDetailPage').then((module) => ({
    default: module.TicketDetailPage,
  })),
)
const TicketsPage = lazy(() =>
  import('../features/tickets/TicketsPage').then((module) => ({
    default: module.TicketsPage,
  })),
)
const SlaSettingsPage = lazy(() =>
  import('../features/sla/SlaSettingsPage').then((module) => ({
    default: module.SlaSettingsPage,
  })),
)
const KnowledgePage = lazy(() =>
  import('../features/knowledge/KnowledgePage').then((module) => ({
    default: module.KnowledgePage,
  })),
)
const KnowledgeArticlePage = lazy(() =>
  import('../features/knowledge/KnowledgeArticlePage').then((module) => ({
    default: module.KnowledgeArticlePage,
  })),
)
const AssetsPage = lazy(() =>
  import('../features/assets/AssetsPage').then((module) => ({
    default: module.AssetsPage,
  })),
)
const AssetDetailPage = lazy(() =>
  import('../features/assets/AssetDetailPage').then((module) => ({
    default: module.AssetDetailPage,
  })),
)
const MonitoringPage = lazy(() =>
  import('../features/monitoring/MonitoringPage').then((module) => ({
    default: module.MonitoringPage,
  })),
)
const AlertsPage = lazy(() =>
  import('../features/alerts/AlertsPage').then((module) => ({
    default: module.AlertsPage,
  })),
)

const AnalyticsPage = lazy(() =>
  import('../features/analytics/AnalyticsPage').then((module) => ({
    default: module.AnalyticsPage,
  })),
)
const AuditPage = lazy(() =>
  import('../features/audit/AuditPage').then((module) => ({
    default: module.AuditPage,
  })),
)

function deferred(element: ReactNode, label: string) {
  return (
    <Suspense
      fallback={
        <main className="centered-page" aria-busy="true">
          <p role="status">Loading {label}…</p>
        </main>
      }
    >
      {element}
    </Suspense>
  )
}

export function App() {
  return (
    <>
      <a className="skip-link" href="#app-content">
        Skip to main content
      </a>
      <div id="app-content" tabIndex={-1}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<FoundationPage />} />
              <Route element={<ProtectedRoute permission="monitoring:view" />}>
                <Route
                  path="/monitoring"
                  element={deferred(<MonitoringPage />, 'monitoring')}
                />
              </Route>
              <Route element={<ProtectedRoute permission="alert:view" />}>
                <Route
                  path="/alerts"
                  element={deferred(<AlertsPage />, 'alerts')}
                />
              </Route>
              <Route element={<ProtectedRoute permission="analytics:view" />}>
                <Route
                  path="/analytics"
                  element={deferred(<AnalyticsPage />, 'command center')}
                />
              </Route>
              <Route element={<ProtectedRoute permission="role:view" />}>
                <Route
                  path="/administration/access"
                  element={deferred(<AccessPage />, 'access management')}
                />
              </Route>
              <Route element={<ProtectedRoute permission="audit:view" />}>
                <Route
                  path="/administration/audit"
                  element={deferred(<AuditPage />, 'audit trail')}
                />
              </Route>
              <Route element={<ProtectedRoute permission="team:view" />}>
                <Route
                  path="/directory"
                  element={deferred(<DirectoryPage />, 'people and teams')}
                />
              </Route>
              <Route element={<ProtectedRoute permission="sla:view" />}>
                <Route
                  path="/administration/sla"
                  element={deferred(<SlaSettingsPage />, 'SLA policies')}
                />
              </Route>
              <Route element={<ProtectedRoute permission="knowledge:view" />}>
                <Route
                  path="/knowledge"
                  element={deferred(<KnowledgePage />, 'knowledge base')}
                />
                <Route
                  path="/knowledge/:articleId"
                  element={deferred(
                    <KnowledgeArticlePage />,
                    'knowledge article',
                  )}
                />
              </Route>
              <Route element={<ProtectedRoute />}>
                <Route
                  path="/tickets"
                  element={deferred(<TicketsPage />, 'ticket queue')}
                />
                <Route
                  path="/tickets/:ticketId"
                  element={deferred(<TicketDetailPage />, 'ticket details')}
                />
              </Route>
              <Route element={<ProtectedRoute />}>
                <Route
                  path="/assets"
                  element={deferred(<AssetsPage />, 'asset inventory')}
                />
                <Route
                  path="/assets/:assetId"
                  element={deferred(<AssetDetailPage />, 'asset details')}
                />
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </div>
    </>
  )
}
