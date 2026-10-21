export default function Loading() {
  return (
    <div className="animate-pulse space-y-4" role="status" aria-label="Loading">
      <div className="h-8 w-56 rounded bg-[#1A222D]" />
      <div className="h-4 w-80 max-w-full rounded bg-[#1A222D]" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="h-24 rounded-[12px] border border-[#26303C] bg-[#121922]" />
        ))}
      </div>
      <div className="h-64 rounded-[12px] border border-[#26303C] bg-[#121922]" />
    </div>
  );
}
