import { useEffect, useState } from "react";
import { getFleet } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";
import ErrorState from "../components/ErrorState.jsx";

export default function FleetBoard({ onOpenAircraft }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  function load() {
    setState({ status: "loading", data: null, error: null });
    getFleet()
      .then((data) => setState({ status: "ready", data, error: null }))
      .catch((error) => setState({ status: "error", data: null, error }));
  }

  useEffect(load, []);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorState error={state.error} onRetry={load} />;

  const aircraft = state.data.aircraft ?? [];
  if (aircraft.length === 0) return <EmptyState message="No aircraft in the fleet." />;

  return (
    <div>
      <h1>Fleet board</h1>
      <div className="card-list">
        {aircraft.map((a) => (
          <button key={a.id} className="card card-clickable" onClick={() => onOpenAircraft(a.id)}>
            <h2>{a.registration}</h2>
            <p className="muted">{a.model}</p>
            <StatusBadge status={a.status} />
            {a.synthetic ? (
              <span className="tag" style={{ marginLeft: 8 }}>
                synthetic
              </span>
            ) : (
              <span className="tag" style={{ marginLeft: 8 }}>
                real — no maintenance records
              </span>
            )}
            <p>{a.reason}</p>
            {a.open_questions > 0 && <p className="muted">{a.open_questions} open question(s)</p>}
          </button>
        ))}
      </div>
    </div>
  );
}
