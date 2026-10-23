"use client";

// Checkboxes for the agree_agents risk setting: a comma-separated list such as "news,earnings".
export function AgreeAgentsField({
  label,
  value,
  choices,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  choices: Array<{ value: string; label: string }>;
  disabled: boolean;
  onChange: (next: string) => void;
}) {
  const chosen = new Set(value.split(",").map((name) => name.trim()).filter(Boolean));
  const toggle = (name: string, on: boolean) => {
    const next = new Set(chosen);
    if (on) next.add(name);
    else next.delete(name);
    // Keep the server's order so the saved value reads the same every time.
    onChange(choices.map((choice) => choice.value).filter((item) => next.has(item)).join(","));
  };
  return (
    <fieldset data-testid="agree-agents" className="rounded border border-[#26303C] bg-[#0F141B] p-3 text-sm">
      <legend className="sr-only">{label}</legend>
      <span className="font-medium" aria-hidden>
        {label}
      </span>
      <span className="mt-1 block text-xs text-[#94A3B8]">A strategy entry is blocked only when these agents are bearish.</span>
      <span className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
        {choices.map((choice) => (
          <label key={choice.value} className="flex items-center gap-2">
            <input type="checkbox" disabled={disabled} checked={chosen.has(choice.value)} onChange={(event) => toggle(choice.value, event.target.checked)} />
            <span>{choice.label}</span>
          </label>
        ))}
      </span>
      {chosen.size === 0 ? <span className="mt-1 block text-xs text-[#EF4444]">Choose at least one agent.</span> : null}
    </fieldset>
  );
}
