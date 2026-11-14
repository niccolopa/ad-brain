import { useEffect, useState } from 'react'
import { getAdDetail, getAdText } from '../api'
import type { AdDetailResponse } from '../types'
import { findQuoteRange } from '../lib/highlight'
import { adPath } from '../lib/router'

export function ADView({ adId, quote, occurrence }: { adId: string; quote?: string; occurrence?: number }) {
  const [detail, setDetail] = useState<AdDetailResponse | null>(null)
  const [text, setText] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null)
    setText(null)
    getAdDetail(adId).then(async (d) => {
      setDetail(d)
      setText(await getAdText(d))
    })
  }, [adId])

  if (!detail || text === null) return <p className="p-6 text-gray-500">Loading AD…</p>

  const activeQuote = quote ?? detail.citations[0]?.quote
  const activeOccurrence = quote ? occurrence ?? 1 : detail.citations[0]?.occurrence ?? 1
  const range = activeQuote ? findQuoteRange(text, activeQuote, activeOccurrence) : null

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{detail.ad.ad_id}</h1>
      <p className="mt-1 text-gray-700 dark:text-gray-300">{detail.ad.title}</p>
      <p className="mt-1 text-sm text-gray-500">
        {detail.ad.authority} · effective {detail.ad.effective_date}
      </p>

      {detail.ad.status === 'superseded' && detail.ad.superseded_by && (
        <p className="mt-2 inline-block rounded bg-red-100 px-2 py-1 text-sm font-semibold text-red-800 dark:bg-red-900/50 dark:text-red-300">
          Superseded by{' '}
          <a href={adPath(detail.ad.superseded_by)} className="underline">
            {detail.ad.superseded_by}
          </a>
        </p>
      )}
      {detail.ad.supersedes.length > 0 && (
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Supersedes:{' '}
          {detail.ad.supersedes.map((id, i) => (
            <span key={id}>
              {i > 0 && ', '}
              <a href={adPath(id)} className="text-blue-700 underline dark:text-blue-400">
                {id}
              </a>
            </span>
          ))}
        </p>
      )}

      <pre className="mt-4 max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded border border-gray-300 bg-gray-50 p-4 font-sans text-sm leading-relaxed text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200">
        {range ? (
          <>
            {text.slice(0, range.start)}
            <mark className="bg-yellow-300 dark:bg-yellow-600 dark:text-black">
              {text.slice(range.start, range.end)}
            </mark>
            {text.slice(range.end)}
          </>
        ) : (
          text
        )}
      </pre>
    </div>
  )
}
