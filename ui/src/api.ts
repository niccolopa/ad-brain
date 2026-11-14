import {
  ApiError,
  type AdDetailResponse,
  type AircraftStatusResponse,
  type DecisionsResponse,
  type DemoResetResponse,
  type FleetResponse,
  type QuestionsResponse,
  type SupersessionResponse,
} from './types'

import fleetMock from './mocks/fleet.json'
import q1Mock from './mocks/q1-aircraft-status.json'
import adDetailMock from './mocks/ad-detail.json'
import q3Mock from './mocks/q3-supersession.json'
import q4Mock from './mocks/q4-decisions.json'
import q5Mock from './mocks/q5-questions.json'
import demoResetMock from './mocks/demo-reset.json'

// Default to mocks: the backend (Core's FastAPI) doesn't exist yet. Flip VITE_USE_MOCKS=false
// once it does; the dev server proxies /api to it (vite.config.ts).
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false'

function notFound(code: string, message: string, details: Record<string, unknown>): never {
  throw new ApiError(404, { error_code: code, message, details })
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) {
    const body = await res
      .json()
      .catch(() => ({ error_code: 'UNKNOWN', message: res.statusText, details: {} }))
    throw new ApiError(res.status, body)
  }
  return res.json()
}

export async function getFleet(): Promise<FleetResponse> {
  if (USE_MOCKS) return fleetMock as FleetResponse
  return fetchJson('/fleet')
}

export async function getAircraftStatus(id: string): Promise<AircraftStatusResponse> {
  if (USE_MOCKS) {
    const full = q1Mock as AircraftStatusResponse
    if (id === full.aircraft.id) return full

    const fleet = fleetMock as FleetResponse
    const entry = fleet.aircraft.find((a) => a.id === id)
    if (!entry) notFound('AIRCRAFT_NOT_FOUND', `No aircraft with id ${id} in this system.`, { id })

    const questions = (q5Mock as QuestionsResponse).questions.filter((q) => q.aircraft_id === id)
    // No full applicable_ads/reasoning_path fixture for this aircraft — synthesize the minimal
    // honest response from what the fleet board and questions mocks actually contain, instead
    // of fabricating ADs we have no fixture for.
    return {
      aircraft: {
        id: entry.id,
        registration: entry.registration,
        model: entry.model,
        serial: entry.serial,
        engine_model: entry.engine_model,
        synthetic: entry.synthetic,
        base: entry.base,
        arc_review_due: entry.arc_review_due,
      },
      status: entry.status,
      summary: entry.reason,
      summary_source: 'template',
      applicable_ads: [],
      superseded_ads: [],
      open_questions: questions,
      hypotheses: [],
      citations: questions.flatMap((q) => q.citations),
      reasoning_path: [],
      computed_at: fleet.computed_at,
    }
  }
  return fetchJson(`/aircraft/${encodeURIComponent(id)}/status`)
}

export async function getAdDetail(adId: string): Promise<AdDetailResponse> {
  if (USE_MOCKS) {
    const mock = adDetailMock as AdDetailResponse
    if (adId === mock.ad.ad_id) return mock
    notFound('AD_NOT_FOUND', `No AD with id ${adId} in this system.`, { ad_id: adId })
  }
  return fetchJson(`/ads/${encodeURIComponent(adId)}`)
}

export async function getAdText(detail: AdDetailResponse): Promise<string> {
  if (!USE_MOCKS) return detail.text
  const basename = detail.ad.file.split('/').pop()
  const res = await fetch(`/ad-texts/${basename}`)
  if (!res.ok) {
    throw new Error(`Mock AD text not found for ${detail.ad.file}. Add it to ui/public/ad-texts/.`)
  }
  return res.text()
}

export async function getSupersession(
  aircraftId: string,
  adId: string,
): Promise<SupersessionResponse> {
  if (USE_MOCKS) {
    const mock = q3Mock as SupersessionResponse
    if (aircraftId === mock.aircraft_id && adId === mock.asked_ad_id) return mock
    notFound(
      'AD_NOT_FOUND',
      `No supersession data for aircraft ${aircraftId} / AD ${adId} in this system.`,
      { aircraft_id: aircraftId, ad_id: adId },
    )
  }
  return fetchJson(
    `/aircraft/${encodeURIComponent(aircraftId)}/ads/${encodeURIComponent(adId)}/supersession`,
  )
}

export async function getDecisions(
  params: { aircraftId?: string; adId?: string } = {},
): Promise<DecisionsResponse> {
  if (USE_MOCKS) {
    const all = (q4Mock as DecisionsResponse).decisions
    const filtered = all.filter(
      (d) =>
        (!params.aircraftId || d.aircraft_id === params.aircraftId) &&
        (!params.adId || d.ad_id === params.adId),
    )
    return { decisions: filtered }
  }
  const qs = new URLSearchParams()
  if (params.aircraftId) qs.set('aircraft_id', params.aircraftId)
  if (params.adId) qs.set('ad_id', params.adId)
  return fetchJson(`/decisions?${qs.toString()}`)
}

export async function getQuestions(aircraftId?: string): Promise<QuestionsResponse> {
  if (USE_MOCKS) {
    const mock = q5Mock as QuestionsResponse
    if (!aircraftId) return mock
    return {
      questions: mock.questions.filter((q) => q.aircraft_id === aircraftId),
      urgency_rule: mock.urgency_rule,
    }
  }
  const qs = aircraftId ? `?aircraft_id=${encodeURIComponent(aircraftId)}` : ''
  return fetchJson(`/questions${qs}`)
}

export async function resetDemo(): Promise<DemoResetResponse> {
  if (USE_MOCKS) return demoResetMock as DemoResetResponse
  return fetchJson('/demo/reset', { method: 'POST' })
}
