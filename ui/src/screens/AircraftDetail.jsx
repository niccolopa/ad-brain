import { useEffect, useState } from "react";
import { getAircraft } from "../api.js";
import StatusBadge from "../components/StatusBadge.jsx";
import SourceQuote from "../components/SourceQuote.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";
import ErrorState from "../components/ErrorState.jsx";

export default function AircraftDetail({ reg, onOpenAD }) {
  const [regInput, setRegInput] = useState(reg ?? "");
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  function load() {
    setState({ status: "loading", data: null, error: null });
    getAircraft(regInput)
      .then((data) => setState({ status: "ready", data, error: null }))
      .catch((error) => setState({ status: "error", data: null, error }));
  }

  useEffect(load, [regInput]);
  useEffect(() => {
    if (reg) setRegInput(reg);
  }, [reg]);

  return (
    <div>
      <h1>Aircraft detail</h1>
      <div style={{ marginBottom: 16 }}>
        <input
          value={regInput}
          onChange={(e) => setRegInput(e.target.value)}
          placeholder="Registration (e.g. DEMO-01)"
        />
        <button onClick={load} style={{ marginLeft: 8 }}>
          Load
        </button>
      </div>

      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorState error={state.error} onRetry={load} />}
      {state.status === "ready" && !state.data && <EmptyState message="No data for this aircraft." />}
      {state.status === "ready" && state.data && (
        <AircraftBody data={state.data} onOpenAD={onOpenAD} />
      )}
    </div>
  );
}

function AircraftBody({ data, onOpenAD }) {
  const { aircraft, status, summary, applicable_ads, superseded_ads, open_questions, hypotheses, citations } = data;

  return (
    <div>
      <div className="card">
        <h2>{aircraft.registration}</h2>
        <p className="muted">
          {aircraft.model} — serial {aircraft.serial} — engine {aircraft.engine_model}
        </p>
        <StatusBadge status={status} />
        <p>{summary}</p>
      </div>

      <h2>Applicable ADs</h2>
      {applicable_ads.length === 0 ? (
        <EmptyState message="No applicable ADs." />
      ) : (
        applicable_ads.map((ad) => (
          <div className="card" key={ad.ad_id}>
            <button className="card-clickable" onClick={() => onOpenAD(ad.ad_id)} style={{ border: "none", padding: 0 }}>
              <h2>{ad.ad_id}</h2>
            </button>
            <p>{ad.title}</p>
            <p className="muted">{ad.applies_because}</p>
            <p>Compliance: {ad.compliance.state}</p>
            {ad.due && <p>Due: {ad.due.text}</p>}
            {ad.citations?.map((c, i) => <SourceQuote key={i} citation={c} />)}
          </div>
        ))
      )}

      {superseded_ads?.length > 0 && (
        <>
          <h2 className="superseded">Superseded ADs</h2>
          <ul>
            {superseded_ads.map((ad) => (
              <li key={ad.ad_id ?? ad}>
                <button className="superseded" onClick={() => onOpenAD(ad.ad_id ?? ad)}>
                  {ad.ad_id ?? ad}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {open_questions?.length > 0 && (
        <>
          <h2>Open questions</h2>
          <ul>
            {open_questions.map((q) => (
              <li key={q.id}>{q.text}</li>
            ))}
          </ul>
        </>
      )}

      {hypotheses?.length > 0 && (
        <>
          <h2>Hypotheses</h2>
          <p className="muted">Informational only — never used to compute status.</p>
          <ul>
            {hypotheses.map((h, i) => (
              <li key={h.id ?? i}>{h.text ?? JSON.stringify(h)}</li>
            ))}
          </ul>
        </>
      )}

      <h2>Citations</h2>
      {citations.map((c, i) => (
        <SourceQuote key={i} citation={c} />
      ))}
    </div>
  );
}
