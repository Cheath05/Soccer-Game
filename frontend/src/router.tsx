import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router'

import Layout from './components/Layout'
import ClubPage from './pages/ClubPage'
import DashboardPage from './pages/DashboardPage'
import FixturesPage from './pages/FixturesPage'
import LeaguePage from './pages/LeaguePage'
import LivePage from './pages/LivePage'
import MatchdayPage from './pages/MatchdayPage'
import MatchReportPage from './pages/MatchReportPage'
import PlayerPage from './pages/PlayerPage'
import SquadPage from './pages/SquadPage'
import TacticsPage from './pages/TacticsPage'

const rootRoute = createRootRoute({ component: Layout })

const routes = [
  createRoute({ getParentRoute: () => rootRoute, path: '/', component: DashboardPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/start', component: () => null }),
  createRoute({ getParentRoute: () => rootRoute, path: '/squad', component: SquadPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/players/$playerId', component: PlayerPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/clubs/$clubId', component: ClubPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/tactics', component: TacticsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/fixtures', component: FixturesPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/league', component: LeaguePage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/matchday', component: MatchdayPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/match/$fixtureId', component: MatchReportPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/live/$fixtureId', component: LivePage }),
]

export const router = createRouter({ routeTree: rootRoute.addChildren(routes) })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
