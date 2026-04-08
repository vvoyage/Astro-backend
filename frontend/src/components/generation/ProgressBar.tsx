export default function ProgressBar({ progress }: { progress: number }) {
  return (
    <div className="h-3 w-full overflow-hidden rounded-full bg-gray-800">
      <div
        className="h-full rounded-full bg-indigo-600 transition-all duration-500"
        style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
      />
    </div>
  );
}
