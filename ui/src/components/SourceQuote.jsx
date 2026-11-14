// Every claim shown to the user is clickable through to its source.
export default function SourceQuote({ citation }) {
  if (!citation) return null;
  return (
    <blockquote className="quote">
      <p>&ldquo;{citation.quote}&rdquo;</p>
      <p className="muted">
        {citation.ad_id} —{" "}
        {citation.source_url ? (
          <a href={citation.source_url} target="_blank" rel="noreferrer">
            source
          </a>
        ) : (
          citation.file
        )}
      </p>
    </blockquote>
  );
}
