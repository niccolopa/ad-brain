export default function EmptyState({ message = "Nothing here yet." }) {
  return <div className="state-box">{message}</div>;
}
