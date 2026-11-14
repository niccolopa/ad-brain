import type { AircraftStatusValue, Urgency } from '../types'

const STATUS_STYLES: Record<AircraftStatusValue, string> = {
  green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  red: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  no_records: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
}

const STATUS_LABELS: Record<AircraftStatusValue, string> = {
  green: 'Green',
  amber: 'Amber',
  red: 'Red',
  no_records: 'No records',
}

export function StatusBadge({ status }: { status: AircraftStatusValue }) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-sm font-semibold ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}

const URGENCY_STYLES: Record<Urgency, string> = {
  overdue: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  high: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  low: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
}

export function UrgencyBadge({ urgency }: { urgency: Urgency }) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-sm font-semibold capitalize ${URGENCY_STYLES[urgency]}`}
    >
      {urgency}
    </span>
  )
}
