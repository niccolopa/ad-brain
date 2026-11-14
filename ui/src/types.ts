// Hand-written from contract/README.md "Shared shapes" + "Object types" (no OpenAPI schema
// from Core yet). Replace with openapi-typescript generated types once Core publishes one —
// see ui/CLAUDE.md "Never hand-write API types."

export type EpistemicClass = 'REGULATION' | 'DECISION' | 'OBSERVATION' | 'HYPOTHESIS' | 'QUESTION'
export type Status = 'active' | 'superseded' | 'contested'
export type AircraftStatusValue = 'green' | 'amber' | 'red' | 'no_records'
export type Urgency = 'low' | 'medium' | 'high' | 'overdue'
export type ReasoningLink =
  | 'supersedes'
  | 'revises'
  | 'appliesTo'
  | 'hasInstalled'
  | 'satisfies'
  | 'madeBy'
  | 'justifiedBy'
  | 'contradicts'

export interface Citation {
  ad_id: string
  quote: string
  file: string
  occurrence: number
  source_url: string
}

export interface ReasoningStep {
  from: string
  link: ReasoningLink
  to: string
  derived: boolean
  note: string
}

export interface ApiErrorBody {
  error_code: string
  message: string
  details: Record<string, unknown>
}

export class ApiError extends Error {
  status: number
  body: ApiErrorBody
  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.status = status
    this.body = body
  }
}

export interface FleetAircraft {
  id: string
  registration: string
  model: string
  serial: string
  engine_model: string
  synthetic: boolean
  base: string
  arc_review_due: string
  status: AircraftStatusValue
  reason: string
  open_questions: number
}

export interface FleetResponse {
  aircraft: FleetAircraft[]
  computed_at: string
}

export interface Aircraft {
  id: string
  registration: string
  model: string
  serial: string
  engine_model: string
  synthetic: boolean
  base: string
  arc_review_due: string
}

export interface Due {
  text: string
  citation: Citation
  overdue: boolean
}

export interface ApplicableAd {
  ad_id: string
  title: string
  epistemic_class: EpistemicClass
  status: Status
  applies_because: string
  compliance: { state: string; record_id: string | null }
  due: Due
  citations: Citation[]
}

export interface AircraftStatusResponse {
  aircraft: Aircraft
  status: AircraftStatusValue
  summary: string
  summary_source: 'template' | 'llm'
  applicable_ads: ApplicableAd[]
  superseded_ads: unknown[]
  open_questions: Question[]
  hypotheses: unknown[]
  citations: Citation[]
  reasoning_path: ReasoningStep[]
  computed_at: string
}

export interface AirworthinessDirective {
  ad_id: string
  authority: 'FAA' | 'EASA'
  title: string
  effective_date: string
  status: Status
  supersedes: string[]
  superseded_by: string | null
  revises: string | null
  source_url: string
  file: string
}

export interface AdDetailResponse {
  ad: AirworthinessDirective
  text: string
  citations: Citation[]
}

export interface SupersessionChainEntry {
  ad_id: string
  status: Status
  superseded_by?: string | null
  effective_date?: string
}

export interface SupersessionResponse {
  aircraft_id: string
  asked_ad_id: string
  chain: SupersessionChainEntry[]
  compliance: {
    id: string
    ad_id: string
    subject_id: string
    date: string
    method: string
    evidence: string
    recorded_by: string
    epistemic_class: EpistemicClass
    synthetic: boolean
  } | null
  still_valid: 'yes' | 'no' | 'unknown'
  reason: string
  citations: Citation[]
  reasoning_path: ReasoningStep[]
}

export interface Person {
  id: string
  name: string
  role: 'mechanic' | 'certifying_engineer' | 'agent'
  synthetic: boolean
}

export interface Decision {
  id: string
  what: string
  aircraft_id: string
  ad_id: string
  rationale: string
  evidence: string[]
  made_by: Person
  made_at: string
  epistemic_class: EpistemicClass
  status: Status
  action_log_id: string
  synthetic: boolean
  citations: Citation[]
  reasoning_path: ReasoningStep[]
}

export interface DecisionsResponse {
  decisions: Decision[]
}

export interface Question {
  id: string
  text: string
  aircraft_id: string
  ad_id: string
  blocks: string
  deadline: string
  deadline_driver: string
  days_left: number
  urgency: Urgency
  epistemic_class: EpistemicClass
  status: Status
  synthetic: boolean
  answer_with: string
  citations: Citation[]
}

export interface QuestionsResponse {
  questions: Question[]
  urgency_rule: string
}

export interface DemoResetResponse {
  ok: boolean
  state: string
  reset_at: string
  counts: Record<string, number>
  not_loaded: string[]
  aircraft_status: Record<string, AircraftStatusValue>
}
