import { useEffect, useState } from "react";
import { getUnknowns } from "../api.js";
import SourceQuote from "../components/SourceQuote.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";
import ErrorState from "../components/ErrorState.jsx";

export default function Unknowns({ onOpenAircraft, onOpenAD }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  function load() {
    setState({ status: "loading", data: null, error: null });
    getUnknowns()
      .then((data) => setState({ status: "ready", data, error: null }))
      .catch((error) => setState({ status: "error", data: null, error }));
  }

  useEffect(load, []);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorState error={state.error} onRetry={load} />;

  const questions = state.data.questions ?? [];

  return (
    <div>
      <h1>Unknowns</h1>
      {state.data.urgency_rule && <p className="muted">{state.data.urgency_rule}</p>}
      {questions.length === 0 ? (
        <EmptyState message="No open questions." />
      ) : (
        questions.map((q) => (
          <div className="card" key={q.id}>
            <p>
              <strong>{q.urgency?.toUpperCase()}</strong> — {q.days_left} day(s) left
            </p>
            <h2>{q.text}</h2>
            <p>
              <button onClick={() => onOpenAircraft(q.aircraft_id)}>{q.aircraft_id}</button>
              {" — "}
              <button onClick={() => onOpenAD(q.ad_id)}>{q.ad_id}</button>
            </p>
            <p className="muted">
              Blocks: {q.blocks} — deadline {q.deadline} ({q.deadline_driver})
            </p>
            {q.citations?.map((c, i) => <SourceQuote key={i} citation={c} />)}
          </div>
        ))
      )}
    </div>
  );
}
