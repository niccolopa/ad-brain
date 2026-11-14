import { useEffect, useState } from 'react'
import { getFleet } from '../api'
import type { FleetResponse } from '../types'
import { StatusBadge } from '../components/StatusBadge'
import { aircraftPath } from '../lib/router'

export function FleetBoard() {
  const [data, setData] = useState<FleetResponse | null>(null)

  useEffect(() => {
    getFleet().then(setData)
  }, [])

  if (!data) return <p className="p-6 text-gray-500">Loading fleet…</p>

  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-semibold text-gray-900 dark:text-gray-100">Fleet board</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data.aircraft.map((a) => (
          <a
            key={a.id}
            href={aircraftPath(a.id)}
            className="rounded-lg border border-gray-300 bg-white p-4 shadow-sm transition hover:border-blue-400 hover:shadow-md dark:border-gray-700 dark:bg-gray-900"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {a.registration}
              </h2>
              <StatusBadge status={a.status} />
            </div>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              {a.model} · {a.serial}
            </p>
            <p className="mt-2 text-sm text-gray-800 dark:text-gray-300">{a.reason}</p>
            {a.open_questions > 0 && (
              <p className="mt-2 text-xs font-medium text-amber-700 dark:text-amber-400">
                {a.open_questions} open question{a.open_questions > 1 ? 's' : ''}
              </p>
            )}
          </a>
        ))}
      </div>
    </div>
  )
}
