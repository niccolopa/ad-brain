export default function ErrorState({ error, onRetry }) {
  const message = error?.message || "Something went wrong.";
  return (
    <div className="state-box">
      <p>{message}</p>
      {onRetry && <button onClick={onRetry}>Retry</button>}
    </div>
  );
}
