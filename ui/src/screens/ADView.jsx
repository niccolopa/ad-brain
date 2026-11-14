import { useEffect, useState } from "react";
import { getAD } from "../api.js";
import SourceQuote from "../components/SourceQuote.jsx";
import Loading from "../components/Loading.jsx";
import EmptyState from "../components/EmptyState.jsx";
import ErrorState from "../components/ErrorState.jsx";

export default function ADView({ adNumber, onOpenAD }) {
  const [adInput, setAdInput] = useState(adNumber ?? "");
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  function load() {
    setState({ status: "loading", data: null, error: null });
    getAD(adInput)
      .then((data) => setState({ status: "ready", data, error: null }))
      .catch((error) => setState({ status: "error", data: null, error }));
  }

  useEffect(load, [adInput]);
  useEffect(() => {
    if (adNumber) setAdInput(adNumber);
  }, [adNumber]);

  return (
    <div>
      <h1>AD view</h1>
      <div style={{ marginBottom: 16 }}>
        <input
          value={adInput}
          onChange={(e) => setAdInput(e.target.value)}
          placeholder="AD number (e.g. FAA:2012-02-02)"
        />
        <button onClick={load} style={{ marginLeft: 8 }}>
          Load
        </button>
      </div>

      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorState error={state.error} onRetry={load} />}
      {state.status === "ready" && !state.data && <EmptyState message="No data for this AD." />}
      {state.status === "ready" && state.data && <ADBody data={state.data} onOpenAD={onOpenAD} />}
    </div>
  );
}

function ADBody({ data, onOpenAD }) {
  const { ad, text, citations } = data;
  const isSuperseded = ad.status === "superseded";

  return (
    <div>
      <div className="card">
        <h2 className={isSuperseded ? "superseded" : undefined}>
          {ad.ad_id} {isSuperseded && "(superseded)"}
        </h2>
        <p className="muted">
          {ad.authority} — effective {ad.effective_date}
        </p>
        <p>{ad.title}</p>

        {ad.superseded_by && (
          <p className="superseded">
            Superseded by{" "}
            <button className="superseded" onClick={() => onOpenAD(ad.superseded_by)}>
              {ad.superseded_by}
            </button>
          </p>
        )}

        {ad.supersedes?.length > 0 && (
          <p>
            Supersedes:{" "}
            {ad.supersedes.map((id) => (
              <button key={id} onClick={() => onOpenAD(id)} style={{ marginRight: 8 }}>
                {id}
              </button>
            ))}
          </p>
        )}

        <a href={ad.source_url} target="_blank" rel="noreferrer">
          Official source
        </a>
      </div>

      <h2>Text</h2>
      <p className="muted">{text}</p>

      <h2>Citations</h2>
      {citations.map((c, i) => (
        <SourceQuote key={i} citation={c} />
      ))}
    </div>
  );
}
