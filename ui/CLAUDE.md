# SURFACE — what the jury sees

Owner: Matteo. The root CLAUDE.md applies; this file adds UI specifics.

## Stack (change these lines if the team picks another)
React + Vite + TypeScript (strict) · Tailwind · Cytoscape.js for the graph.
API types are generated from Core's OpenAPI schema with openapi-typescript.
Never hand-write API types.

## Screens (only these five)
1. Fleet board: one card per aircraft, green / amber / red, with a one-line reason.
2. Aircraft detail: applicable ADs, the reasoning path drawn on the graph, the answer with citations.
3. AD view: AD text with the cited sentence highlighted. Superseded ADs in red, linked to the
   AD that replaced them.
4. Decision ledger: who decided what, when, why, with evidence.
5. Unknowns panel: open QUESTIONs sorted by urgency, with the deadline that drives it.

## Rules
- Mock mode: when VITE_USE_MOCKS=true, responses come from ui/src/mocks/*.json, copied from
  contract/examples/. The UI must run fully on mocks before the backend exists.
  If the contract changes, re-copy the examples.
- Never a white screen: an error boundary at the root, and every request has loading, empty
  and error states.
- Every claim shown to the user has a clickable citation. No claim without a source.
- Wow features (graph animation, live AD ingestion, RAG comparison) sit behind flags in one
  config file.
- A "Reset demo" control calls the reset endpoint.
- Real aircraft carry a "real — no maintenance records" badge and never a red "grounded"
  status. Synthetic aircraft carry a "synthetic" badge.
- Visual direction: calm, dense, operational. Colour carries meaning only: status
  (green / amber / red) and superseded (red).
- Projector-ready: base font at least 16 px, high contrast, works at 1280×720.
