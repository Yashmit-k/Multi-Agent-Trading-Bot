"use client";

import { OPS, type Condition, type Operand, type OperandInfo } from "@/components/strategy/types";

const box = "rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1 text-sm disabled:opacity-60";

function OperandPicker({ value, onChange, catalog, allowNumber, disabled }: { value: Operand; onChange: (next: Operand) => void; catalog: OperandInfo[]; allowNumber: boolean; disabled?: boolean }) {
  const isNumber = value.value !== undefined && value.value !== null;
  const info = catalog.find((item) => item.indicator === value.indicator);
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <select
        aria-label="Operand"
        className={box}
        disabled={disabled}
        value={isNumber ? "__number" : value.indicator ?? "close"}
        onChange={(event) => {
          const choice = event.target.value;
          if (choice === "__number") onChange({ value: 50 });
          else {
            const picked = catalog.find((item) => item.indicator === choice);
            onChange({ indicator: choice, period: picked?.needs_period ? value.period ?? 14 : null });
          }
        }}
      >
        {catalog.map((item) => (
          <option key={item.indicator} value={item.indicator}>
            {item.label}
          </option>
        ))}
        {allowNumber ? <option value="__number">A number…</option> : null}
      </select>
      {isNumber ? (
        <input aria-label="Number" type="number" step="any" className={`${box} w-24`} disabled={disabled} value={String(value.value)} onChange={(event) => onChange({ value: Number(event.target.value) })} />
      ) : info?.needs_period ? (
        <input
          aria-label="Period"
          type="number"
          min={1}
          max={400}
          className={`${box} w-20`}
          disabled={disabled}
          value={String(value.period ?? 14)}
          onChange={(event) => onChange({ indicator: value.indicator, period: Number(event.target.value) })}
        />
      ) : null}
    </span>
  );
}

export function ConditionList({
  title,
  hint,
  conditions,
  onChange,
  catalog,
  minimum,
  disabled,
}: {
  title: string;
  hint: string;
  conditions: Condition[];
  onChange: (next: Condition[]) => void;
  catalog: OperandInfo[];
  minimum: number;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-2">
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-xs text-[#64748B]">{hint}</p>
      </div>
      {conditions.map((condition, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2 rounded border border-[#1E2631] bg-[#0F141B] p-2">
          <span className="w-10 text-xs text-[#64748B]">{index === 0 ? "If" : title.startsWith("Exit") ? "or" : "and"}</span>
          <OperandPicker value={condition.left} catalog={catalog} allowNumber={false} disabled={disabled} onChange={(left) => onChange(conditions.map((item, k) => (k === index ? { ...item, left } : item)))} />
          <select aria-label="Comparison" className={box} disabled={disabled} value={condition.op} onChange={(event) => onChange(conditions.map((item, k) => (k === index ? { ...item, op: event.target.value } : item)))}>
            {OPS.map(([op, label]) => (
              <option key={op} value={op}>
                {label}
              </option>
            ))}
          </select>
          <OperandPicker value={condition.right} catalog={catalog} allowNumber disabled={disabled} onChange={(right) => onChange(conditions.map((item, k) => (k === index ? { ...item, right } : item)))} />
          <button
            type="button"
            disabled={disabled || conditions.length <= minimum}
            className="ml-auto text-xs text-[#94A3B8] hover:text-[#EF4444] disabled:opacity-40"
            onClick={() => onChange(conditions.filter((_, k) => k !== index))}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        disabled={disabled || conditions.length >= 8}
        className="rounded border border-dashed border-[#26303C] px-2 py-1 text-xs text-[#94A3B8] hover:text-[#E6EDF3] disabled:opacity-40"
        onClick={() => onChange([...conditions, { left: { indicator: "rsi", period: 14 }, op: ">", right: { value: 50 } }])}
      >
        + Add condition
      </button>
    </div>
  );
}
