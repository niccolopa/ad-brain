// Colour carries meaning only. Red is reserved for the synthetic fleet;
// a real aircraft with no maintenance records is grey, never red.
const LABELS = {
  green: { text: "Green", className: "badge-green" },
  amber: { text: "Amber", className: "badge-amber" },
  red: { text: "Red", className: "badge-red" },
  no_records: { text: "To verify against logbooks", className: "badge-grey" },
};

export default function StatusBadge({ status }) {
  const info = LABELS[status] ?? { text: status ?? "Unknown", className: "badge-grey" };
  return <span className={`badge ${info.className}`}>{info.text}</span>;
}
