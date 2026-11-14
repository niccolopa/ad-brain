import { useEffect, useState } from 'react'
import { getQuestions } from '../api'
import type { QuestionsResponse, Urgency } from '../types'
import { UrgencyBadge } from '../components/StatusBadge'
import { SourceQuote } from '../components/SourceQuote'
import { aircraftPath } from '../lib/router'

const URGENCY_RANK: Record<Urgency, number> = { overdue: 0, high: 1, medium: 2, low: 3 }

export function Unknowns() {
  const [data, setData] = useState<QuestionsResponse | null>(null)

  useEffect(() => {
    getQuestions().then(setData)
  }, [])

  if (!data) return <p className="p-6 text-gray-500">Loading open questions…</p>

  const sorted = [...data.questions].sort(
    (a, b) => URGENCY_RANK[a.urgency] - URGENCY_RANK[b.urgency] || a.days_left - b.days_left,
  )

  return (
    <div className="p-6">
      <h1 className="mb-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">Unknowns</h1>
      <p className="mb-4 text-sm text-gray-500">{data.urgency_rule}</p>
      {sorted.length === 0 ? (
        <p className="text-gray-500">No open questions.</p>
      ) : (
        <ul className="space-y-4">
          {sorted.map((q) => (
            <li key={q.id} className="rounded border border-gray-300 p-4 dark:border-gray-700">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold text-gray-900 dark:text-gray-100">{q.text}</p>
                <UrgencyBadge urgency={q.urgency} />
              </div>
              <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                Blocks {q.blocks} · deadline {q.deadline} ({q.deadline_driver}) · {q.days_left} days left
              </p>
              <p className="mt-1 text-sm text-gray-500">
                Aircraft:{' '}
                <a href={aircraftPath(q.aircraft_id)} className="text-blue-700 underline dark:text-blue-400">
                  {q.aircraft_id}
                </a>
              </p>
              <div className="mt-2 space-y-2">
                {q.citations.map((c, i) => (
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
