export function PageFrame({
  title,
  description,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold text-[#E6EDF3]">{title}</h1>
        {description ? <div className="mt-1 text-sm text-[#94A3B8]">{description}</div> : null}
      </header>
      {children}
    </div>
  );
}
