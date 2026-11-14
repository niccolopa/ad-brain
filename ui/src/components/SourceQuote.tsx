import type { Citation } from '../types'
import { adPath } from '../lib/router'

// ui/CLAUDE.md: "Every claim shown to the user has a clickable citation."
export function SourceQuote({ citation }: { citation: Citation }) {
  return (
    <a
      href={adPath(citation.ad_id, { quote: citation.quote, occurrence: citation.occurrence })}
      className="block rounded border border-gray-300 bg-gray-50 px-3 py-2 text-sm hover:border-blue-400 dark:border-gray-700 dark:bg-gray-800/60 dark:hover:border-blue-500"
    >
      <span className="italic text-gray-700 dark:text-gray-300">&ldquo;{citation.quote}&rdquo;</span>
      <span className="ml-2 whitespace-nowrap text-xs font-semibold text-blue-700 dark:text-blue-400">
        {citation.ad_id} →
      </span>
    </a>
  )
}
