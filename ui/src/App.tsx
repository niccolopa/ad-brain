import { useHashRoute, fleetPath, decisionsPath, questionsPath } from './lib/router'
import { FleetBoard } from './screens/FleetBoard'
import { AircraftDetail } from './screens/AircraftDetail'
import { ADView } from './screens/ADView'
import { DecisionLedger } from './screens/DecisionLedger'
import { Unknowns } from './screens/Unknowns'

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      className="rounded px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-200 dark:text-gray-300 dark:hover:bg-gray-800"
    >
      {children}
    </a>
  )
}

function App() {
  const route = useHashRoute()

  return (
    <div className="min-h-svh bg-gray-100 dark:bg-gray-950">
      <nav className="flex items-center gap-1 border-b border-gray-300 bg-white px-4 py-2 dark:border-gray-800 dark:bg-gray-900">
        <span className="mr-3 text-base font-bold text-gray-900 dark:text-gray-100">AD Brain</span>
        <NavLink href={fleetPath()}>Fleet board</NavLink>
        <NavLink href={decisionsPath()}>Decision ledger</NavLink>
        <NavLink href={questionsPath()}>Unknowns</NavLink>
      </nav>

      <main>
        {route.name === 'fleet' && <FleetBoard />}
        {route.name === 'aircraft' && <AircraftDetail id={route.id} />}
        {route.name === 'ad' && (
          <ADView adId={route.adId} quote={route.quote} occurrence={route.occurrence} />
        )}
        {route.name === 'decisions' && <DecisionLedger />}
        {route.name === 'questions' && <Unknowns />}
      </main>
    </div>
  )
}

export default App
