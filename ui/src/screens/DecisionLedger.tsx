import { useEffect, useState } from 'react'
import { getDecisions } from '../api'
import type { DecisionsResponse } from '../types'
import { SourceQuote } from '../components/SourceQuote'
import { aircraftPath, adPath } from '../lib/router'

export function DecisionLedger() {
  const [data, setData] = useState<DecisionsResponse | null>(null)

  useEffect(() => {
    getDecisions().then(setData)
  }, [])

  if (!data) return <p className="p-6 text-gray-500">Loading decisions…</p>

  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-semibold text-gray-900 dark:text-gray-100">Decision ledger</h1>
      {data.decisions.length === 0 ? (
        <p className="text-gray-500">No decisions recorded yet.</p>
      ) : (
        <ul className="space-y-4">
          {data.decisions.map((d) => (
            <li key={d.id} className="rounded border border-gray-300 p-4 dark:border-gray-700">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-semibold text-gray-900 dark:text-gray-100">
                  {d.what.replace(/_/g, ' ')} —{' '}
                  <a href={aircraftPath(d.aircraft_id)} className="text-blue-700 underline dark:text-blue-400">
                    {d.aircraft_id}
                  </a>{' '}
                  /{' '}
                  <a href={adPath(d.ad_id)} className="text-blue-700 underline dark:text-blue-400">
                    {d.ad_id}
                  </a>
                </p>
                <p className="text-sm text-gray-500">{d.made_at}</p>
              </div>
              <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{d.rationale}</p>
              <p className="mt-1 text-xs text-gray-500">
                Made by {d.made_by.name} ({d.made_by.role})
                {d.synthetic && ' · synthetic'}
              </p>
              <div className="mt-2 space-y-2">
                {d.citations.map((c, i) => (
                  <SourceQuote key={i} citation={c} />
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
