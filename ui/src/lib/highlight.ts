// Matches contract/README.md "A `quote` matches a span of the file after collapsing every
// whitespace run ... to one space, in both the quote and the file." Finds the nth (1-indexed)
// occurrence and maps it back to an offset range in the ORIGINAL (uncollapsed) text, so the UI
// can highlight the real text without reformatting it.

export interface HighlightRange {
  start: number
  end: number
}

function collapseWithMap(text: string): { collapsed: string; map: number[] } {
  let collapsed = ''
  const map: number[] = []
  let inWhitespace = false
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (/\s/.test(ch)) {
      if (!inWhitespace) {
        collapsed += ' '
        map.push(i)
        inWhitespace = true
      }
    } else {
      collapsed += ch
      map.push(i)
      inWhitespace = false
    }
  }
  return { collapsed, map }
}

export function findQuoteRange(text: string, quote: string, occurrence: number): HighlightRange | null {
  if (occurrence < 1) return null
  const { collapsed, map } = collapseWithMap(text)
  const collapsedQuote = collapseWithMap(quote).collapsed.trim()
  if (!collapsedQuote) return null

  let fromIndex = 0
  let foundAt = -1
  for (let n = 0; n < occurrence; n++) {
    foundAt = collapsed.indexOf(collapsedQuote, fromIndex)
    if (foundAt === -1) return null
    fromIndex = foundAt + 1
  }

  const startOrig = map[foundAt]
  const lastCollapsedIdx = foundAt + collapsedQuote.length - 1
  const endOrig = map[lastCollapsedIdx] + 1
  return { start: startOrig, end: endOrig }
}
