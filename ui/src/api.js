// The ONLY place in the UI that fetches data. Screens call these functions
// and never touch fetch() or the mocks directly — contract/README.md is the
// source of truth for every field name here; nothing is renamed or invented.

export const API_URL = "http://localhost:8000";
export const USE_MOCKS = true;

import fleetMock from "./mocks/fleet.json";
import aircraftStatusMock from "./mocks/q1-aircraft-status.json";
import adDetailMock from "./mocks/ad-detail.json";
import decisionsMock from "./mocks/q4-decisions.json";
import questionsMock from "./mocks/q5-questions.json";

async function fromApi(path) {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw await toApiError(res);
  return res.json();
}

async function toApiError(res) {
  try {
    const body = await res.json();
    return Object.assign(new Error(body.message || `Request failed (${res.status})`), body);
  } catch {
    return new Error(`Request failed (${res.status})`);
  }
}

// GET /fleet
export async function getFleet() {
  if (USE_MOCKS) return fleetMock.response.body;
  return fromApi("/fleet");
}

// Q1 — GET /aircraft/{id}/status
export async function getAircraft(reg) {
  if (USE_MOCKS) return aircraftStatusMock.response.body;
  return fromApi(`/aircraft/${encodeURIComponent(reg)}/status`);
}

// GET /ads/{ad_id}
export async function getAD(adNumber) {
  if (USE_MOCKS) return adDetailMock.response.body;
  return fromApi(`/ads/${encodeURIComponent(adNumber)}`);
}

// Q4 — GET /decisions?ad_id=
export async function getDecisions(adNumber) {
  if (USE_MOCKS) return decisionsMock.response.body;
  const query = adNumber ? `?ad_id=${encodeURIComponent(adNumber)}` : "";
  return fromApi(`/decisions${query}`);
}

// Q5 — GET /questions
export async function getUnknowns() {
  if (USE_MOCKS) return questionsMock.response.body;
  return fromApi("/questions");
}
