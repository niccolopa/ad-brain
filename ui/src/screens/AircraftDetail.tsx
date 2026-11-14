import { useEffect, useRef, useState } from 'react'
import cytoscape from 'cytoscape'
import { getAircraftStatus } from '../api'
import type { AircraftStatusResponse } from '../types'
import { StatusBadge } from '../components/StatusBadge'
import { SourceQuote } from '../components/SourceQuote'
import { fleetPath } from '../lib/router'

function ReasoningGraph({ data }: { data: AircraftStatusResponse }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current || data.reasoning_path.length === 0) return

    const nodes = new Map<string, { id: string; label: string; kind: string }>()
    nodes.set(data.aircraft.id, {
      id: data.aircraft.id,
      label: data.aircraft.registration,
      kind: 'aircraft',
    })
    for (const ad of data.applicable_ads) {
      nodes.set(ad.ad_id, { id: ad.ad_id, label: ad.ad_id, kind: 'ad' })
    }
    for (const step of data.reasoning_path) {
      if (!nodes.has(step.from)) nodes.set(step.from, { id: step.from, label: step.from, kind: 'other' })
      if (!nodes.has(step.to)) nodes.set(step.to, { id: step.to, label: step.to, kind: 'other' })
    }

    const elements = [
      ...[...nodes.values()].map((n) => ({ data: { id: n.id, label: n.label }, classes: n.kind })),
      ...data.reasoning_path.map((step, i) => ({
        data: { id: `e${i}`, source: step.from, target: step.to, label: step.link },
        classes: step.derived ? 'derived' : '',
      })),
    ]

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'text-valign': 'center',
            color: '#111827',
            'font-size': 12,
            width: 'label',
            height: 'label',
            padding: '10px',
            shape: 'round-rectangle',
            'background-color': '#e5e7eb',
            'border-width': 1,
            'border-color': '#9ca3af',
          },
        },
        { selector: 'node.aircraft', style: { 'background-color': '#bfdbfe', 'border-color': '#3b82f6' } },
        { selector: 'node.ad', style: { 'background-color': '#fde68a', 'border-color': '#d97706' } },
        {
          selector: 'edge',
          style: {
            width: 2,
            'line-color': '#9ca3af',
            'target-arrow-color': '#9ca3af',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': 10,
            color: '#374151',
            'text-rotation': 'autorotate',
          },
        },
        { selector: 'edge.derived', style: { 'line-style': 'dashed' } },
      ],
      layout: { name: 'breadthfirst', directed: true, padding: 20 },
    })

    return () => cy.destroy()
  }, [data])

  if (data.reasoning_path.length === 0) {
    return (
      <p className="rounded border border-dashed border-gray-300 p-4 text-sm text-gray-500 dark:border-gray-700">
        No reasoning path recorded for this aircraft yet.
      </p>
    )
  }

  return (
    <div
      ref={containerRef}
      className="h-80 w-full rounded border border-gray-300 bg-white dark:border-gray-700 dark:bg-gray-900"
    />
  )
}

export function AircraftDetail({ id }: { id: string }) {
  const [data, setData] = useState<AircraftStatusResponse | null>(null)

  useEffect(() => {
    setData(null)
    getAircraftStatus(id).then(setData)
  }, [id])

  if (!data) return <p className="p-6 text-gray-500">Loading aircraft…</p>

  return (
    <div className="p-6">
      <a href={fleetPath()} className="text-sm text-blue-700 hover:underline dark:text-blue-400">
        ← Fleet board
      </a>
      <div className="mt-2 flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
          {data.aircraft.registration}
        </h1>
        <StatusBadge status={data.status} />
      </div>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        {data.aircraft.model} · {data.aircraft.serial} · {data.aircraft.engine_model}
      </p>
      <p className="mt-3 text-gray-800 dark:text-gray-300">{data.summary}</p>

      <h2 className="mt-6 text-lg font-semibold text-gray-900 dark:text-gray-100">Reasoning path</h2>
      <div className="mt-2">
        <ReasoningGraph data={data} />
      </div>

      <h2 className="mt-6 text-lg font-semibold text-gray-900 dark:text-gray-100">Applicable ADs</h2>
      {data.applicable_ads.length === 0 ? (
        <p className="mt-2 text-sm text-gray-500">No applicable AD on record for this aircraft.</p>
      ) : (
        <ul className="mt-2 space-y-4">
          {data.applicable_ads.map((ad) => (
            <li key={ad.ad_id} className="rounded border border-gray-300 p-4 dark:border-gray-700">
              <p className="font-semibold text-gray-900 dark:text-gray-100">
                {ad.ad_id} — {ad.title}
              </p>
              <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{ad.applies_because}</p>
              <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{ad.due.text}</p>
              <div className="mt-2 space-y-2">
                {ad.citations.map((c, i) => (
                  <SourceQuote key={i} citation={c} />
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}

      {data.open_questions.length > 0 && (
        <>
          <h2 className="mt-6 text-lg font-semibold text-gray-900 dark:text-gray-100">Open questions</h2>
          <ul className="mt-2 space-y-2">
            {data.open_questions.map((q) => (
              <li key={q.id} className="rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-900/20">
                {q.text}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
