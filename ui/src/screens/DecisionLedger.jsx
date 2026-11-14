import { useEffect, useState } from "react";
import { getDecisions } from "../api.js";
import SourceQuote from "../components/SourceQuote.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";
import ErrorState from "../components/ErrorState.jsx";

export default function DecisionLedger({ onOpenAircraft, onOpenAD }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  function load() {
    setState({ status: "loading", data: null, error: null });
    getDecisions()
      .then((data) => setState({ status: "ready", data, error: null }))
      .catch((error) => setState({ status: "error", data: null, error }));
  }

  useEffect(load, []);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorState error={state.error} onRetry={load} />;

  const decisions = state.data.decisions ?? [];

  return (
    <div>
      <h1>Decision ledger</h1>
      {decisions.length === 0 ? (
        <EmptyState message="No decisions recorded yet." />
      ) : (
        decisions.map((d) => (
          <div className="card" key={d.id}>
            <h2>{d.what}</h2>
            <p>
              <button onClick={() => onOpenAircraft(d.aircraft_id)}>{d.aircraft_id}</button>
              {" — "}
              <button onClick={() => onOpenAD(d.ad_id)}>{d.ad_id}</button>
            </p>
            <p>{d.rationale}</p>
            <p className="muted">
              {d.made_by?.name} ({d.made_by?.role}) — {d.made_at}
            </p>
            <ul>
              {d.evidence?.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
            {d.citations?.map((c, i) => <SourceQuote key={i} citation={c} />)}
          </div>
        ))
      )}
    </div>
  );
}
