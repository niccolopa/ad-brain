import { useState } from "react";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import FleetBoard from "./screens/FleetBoard.jsx";
import AircraftDetail from "./screens/AircraftDetail.jsx";
import ADView from "./screens/ADView.jsx";
import DecisionLedger from "./screens/DecisionLedger.jsx";
import Unknowns from "./screens/Unknowns.jsx";

const SCREENS = [
  { key: "fleet", label: "Fleet board" },
  { key: "aircraft", label: "Aircraft detail" },
  { key: "ad", label: "AD view" },
  { key: "decisions", label: "Decision ledger" },
  { key: "unknowns", label: "Unknowns" },
];

export default function App() {
  const [view, setView] = useState({ screen: "fleet" });

  function openAircraft(reg) {
    setView({ screen: "aircraft", reg });
  }

  function openAD(adNumber) {
    setView({ screen: "ad", adNumber });
  }

  function goTo(screen) {
    setView({ screen });
  }

  return (
    <ErrorBoundary>
      <nav>
        {SCREENS.map((s) => (
          <button key={s.key} aria-current={view.screen === s.key} onClick={() => goTo(s.key)}>
            {s.label}
          </button>
        ))}
      </nav>

      {view.screen === "fleet" && <FleetBoard onOpenAircraft={openAircraft} />}
      {view.screen === "aircraft" && <AircraftDetail reg={view.reg} onOpenAD={openAD} />}
      {view.screen === "ad" && <ADView adNumber={view.adNumber} onOpenAD={openAD} />}
      {view.screen === "decisions" && (
        <DecisionLedger onOpenAircraft={openAircraft} onOpenAD={openAD} />
      )}
      {view.screen === "unknowns" && <Unknowns onOpenAircraft={openAircraft} onOpenAD={openAD} />}
    </ErrorBoundary>
  );
}
