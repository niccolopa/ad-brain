import { useEffect, useState } from 'react'

// Five screens, simple nesting — a hand-rolled hash router avoids pulling in react-router
// for a surface this small (see ui/CLAUDE.md dependency policy: no new deps without asking).
export type Route =
  | { name: 'fleet' }
  | { name: 'aircraft'; id: string }
  | { name: 'ad'; adId: string; quote?: string; occurrence?: number }
  | { name: 'decisions' }
  | { name: 'questions' }

function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, '') || '/'
  const [pathname, search] = path.split('?')
  const params = new URLSearchParams(search ?? '')
  const segments = pathname.split('/').filter(Boolean)

  if (segments[0] === 'aircraft' && segments[1]) {
    return { name: 'aircraft', id: decodeURIComponent(segments[1]) }
  }
  if (segments[0] === 'ads' && segments[1]) {
    const occurrence = params.get('occurrence')
    return {
      name: 'ad',
      adId: decodeURIComponent(segments[1]),
      quote: params.get('quote') ?? undefined,
      occurrence: occurrence ? Number(occurrence) : undefined,
    }
  }
  if (segments[0] === 'decisions') return { name: 'decisions' }
  if (segments[0] === 'questions') return { name: 'questions' }
  return { name: 'fleet' }
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export function fleetPath(): string {
  return '#/'
}

export function aircraftPath(id: string): string {
  return `#/aircraft/${encodeURIComponent(id)}`
}

export function adPath(adId: string, opts?: { quote?: string; occurrence?: number }): string {
  let path = `#/ads/${encodeURIComponent(adId)}`
  if (opts?.quote) {
    const qs = new URLSearchParams()
    qs.set('quote', opts.quote)
    if (opts.occurrence) qs.set('occurrence', String(opts.occurrence))
    path += `?${qs.toString()}`
  }
  return path
}

export function decisionsPath(): string {
  return '#/decisions'
}

export function questionsPath(): string {
  return '#/questions'
}
