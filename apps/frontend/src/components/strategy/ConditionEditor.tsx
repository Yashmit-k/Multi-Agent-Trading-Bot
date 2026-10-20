"use client";

import { useState } from "react";
import { OPS, higherTimeframes, isGroup, type Condition, type Group, type Operand, type OperandInfo, type Timeframe } from "@/components/strategy/types";

const box = "rounded border border-[#26303C] bg-[#0B0F14] px-2 py-1 text-sm disabled:opacity-60";
const small = `${box} w-16`;

export function OperandPicker({
  value,
  onChange,
  catalog,
  timeframe,
  allowNumber = true,
}: {
  value: Operand;
  onChange: (next: Operand) => void;
  catalog: OperandInfo[];
  timeframe: Timeframe;
  allowNumber?: boolean;
}) {
  const [advanced, setAdvanced] = useState(Boolean(value.timeframe || value.offset || (value.scale ?? 1) !== 1 || value.shift));
  const isNumber = value.value !== undefined && value.value !== null;
  const info = catalog.find((item) => item.indicator === value.indicator);
  const groups = Array.from(new Set(catalog.map((item) => item.group)));
  const higher = higherTimeframes(timeframe);
  const set = (patch: Partial<Operand>) => onChange({ ...value, ...patch });
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <select
        aria-label="Operand"
        className={box}
        value={isNumber ? "__number" : value.indicator ?? "close"}
        onChange={(event) => {
          const choice = event.target.value;
          if (choice === "__number") onChange({ value: 50 });
          else {
            const picked = catalog.find((item) => item.indicator === choice);
            onChange({ indicator: choice, period: picked?.needs_period ? value.period ?? picked.default_period ?? 14 : null, timeframe: value.timeframe ?? null });
          }
        }}
      >
        {groups.map((group) => (
          <optgroup key={group} label={group}>
            {catalog
              .filter((item) => item.group === group)
              .map((item) => (
                <option key={item.indicator} value={item.indicator}>
                  {item.label}
                </option>
              ))}
          </optgroup>
        ))}
        {allowNumber ? (
          <optgroup label="Value">
            <option value="__number">A number…</option>
          </optgroup>
        ) : null}
      </select>
      {isNumber ? (
        <input aria-label="Number" type="number" step="any" className={`${box} w-24`} value={String(value.value)} onChange={(event) => onChange({ value: Number(event.target.value) })} />
      ) : (
        <>
          {info?.needs_period || info?.default_period ? (
            <input aria-label="Period" title="Period" type="number" min={1} max={500} className={small} value={String(value.period ?? info?.default_period ?? "")} onChange={(event) => set({ period: Number(event.target.value) })} />
          ) : null}
          {info?.uses_period2 ? (
            <input aria-label="Second period" title={info.indicator.startsWith("macd") ? "Slow period" : "Smoothing"} type="number" min={1} max={500} className={small} placeholder={info.indicator.startsWith("macd") ? "26" : "3"} value={value.period2 == null ? "" : String(value.period2)} onChange={(event) => set({ period2: event.target.value ? Number(event.target.value) : null })} />
          ) : null}
          {info?.uses_param ? (
            <input aria-label="Multiplier" title="Multiplier" type="number" step="0.1" min={0.1} max={20} className={small} placeholder={info.indicator.startsWith("supertrend") ? "3" : "2"} value={value.param == null ? "" : String(value.param)} onChange={(event) => set({ param: event.target.value ? Number(event.target.value) : null })} />
          ) : null}
          <button type="button" className="text-[10px] text-[#60A5FA]" onClick={() => setAdvanced(!advanced)}>
            {advanced ? "less" : "more…"}
          </button>
          {advanced ? (
            <span className="inline-flex flex-wrap items-center gap-1 rounded border border-dashed border-[#26303C] px-1 py-0.5 text-[10px] text-[#94A3B8]">
              {higher.length ? (
                <label className="flex items-center gap-1">
                  from
                  <select className={box} value={value.timeframe ?? ""} onChange={(event) => set({ timeframe: (event.target.value || null) as Timeframe | null })}>
                    <option value="">this timeframe</option>
                    {higher.map((tf) => (
                      <option key={tf} value={tf}>
                        {tf} (completed bars)
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label className="flex items-center gap-1">
                bars ago
                <input type="number" min={0} max={500} className={small} value={String(value.offset ?? 0)} onChange={(event) => set({ offset: Number(event.target.value) })} />
              </label>
              <label className="flex items-center gap-1">
                ×
                <input type="number" step="any" className={small} value={String(value.scale ?? 1)} onChange={(event) => set({ scale: Number(event.target.value) })} />
              </label>
              <label className="flex items-center gap-1">
                +
                <input type="number" step="any" className={small} value={String(value.shift ?? 0)} onChange={(event) => set({ shift: Number(event.target.value) })} />
              </label>
            </span>
          ) : null}
        </>
      )}
    </span>
  );
}

function ConditionRow({ condition, onChange, onRemove, catalog, timeframe, lead }: { condition: Condition; onChange: (next: Condition) => void; onRemove: () => void; catalog: OperandInfo[]; timeframe: Timeframe; lead: string }) {
  const [more, setMore] = useState(Boolean((condition.for_bars ?? 1) > 1 || (condition.within_bars ?? 1) > 1));
  return (
    <div className="flex flex-wrap items-center gap-2 rounded border border-[#1E2631] bg-[#0F141B] p-2">
      <span className="w-10 text-xs text-[#64748B]">{lead}</span>
      <OperandPicker value={condition.left} catalog={catalog} timeframe={timeframe} allowNumber={false} onChange={(left) => onChange({ ...condition, left })} />
      <select aria-label="Comparison" className={box} value={condition.op} onChange={(event) => onChange({ ...condition, op: event.target.value })}>
        {OPS.map(([op, label]) => (
          <option key={op} value={op}>
            {label}
          </option>
        ))}
      </select>
      <OperandPicker value={condition.right} catalog={catalog} timeframe={timeframe} onChange={(right) => onChange({ ...condition, right })} />
      <button type="button" className="text-[10px] text-[#60A5FA]" onClick={() => setMore(!more)}>
        {more ? "hide timing" : "timing…"}
      </button>
      {more ? (
        <span className="inline-flex items-center gap-2 text-[10px] text-[#94A3B8]">
          <label className="flex items-center gap-1">
            true for
            <input type="number" min={1} max={200} className={small} value={String(condition.for_bars ?? 1)} onChange={(event) => onChange({ ...condition, for_bars: Number(event.target.value) })} />
            bars in a row
          </label>
          <label className="flex items-center gap-1">
            or within the last
            <input type="number" min={1} max={200} className={small} value={String(condition.within_bars ?? 1)} onChange={(event) => onChange({ ...condition, within_bars: Number(event.target.value) })} />
            bars
          </label>
        </span>
      ) : null}
      <button type="button" className="ml-auto text-xs text-[#94A3B8] hover:text-[#EF4444]" onClick={onRemove}>
        Remove
      </button>
    </div>
  );
}

const NEW_CONDITION: Condition = { left: { indicator: "rsi", period: 14 }, op: ">", right: { value: 50 } };

export function GroupEditor({ group, onChange, onRemove, catalog, timeframe, depth = 0 }: { group: Group; onChange: (next: Group) => void; onRemove?: () => void; catalog: OperandInfo[]; timeframe: Timeframe; depth?: number }) {
  const update = (index: number, next: Group | Condition) => onChange({ ...group, items: group.items.map((item, k) => (k === index ? next : item)) });
  const remove = (index: number) => onChange({ ...group, items: group.items.filter((_, k) => k !== index) });
  const word = group.logic === "all" ? "and" : "or";
  return (
    <div className={`space-y-2 rounded border p-2 ${depth ? "border-[#2563EB]/40 bg-[#0B0F14]" : "border-transparent"}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select aria-label="Group logic" className={box} value={group.logic} onChange={(event) => onChange({ ...group, logic: event.target.value as "all" | "any" })}>
          <option value="all">ALL of these are true</option>
          <option value="any">ANY of these is true</option>
        </select>
        <label className="flex items-center gap-1 text-[#94A3B8]">
          <input type="checkbox" checked={Boolean(group.negate)} onChange={(event) => onChange({ ...group, negate: event.target.checked })} />
          NOT (invert this group)
        </label>
        {onRemove ? (
          <button type="button" className="ml-auto text-[#94A3B8] hover:text-[#EF4444]" onClick={onRemove}>
            Remove group
          </button>
        ) : null}
      </div>
      {group.items.map((item, index) =>
        isGroup(item) ? (
          <GroupEditor key={index} group={item} depth={depth + 1} catalog={catalog} timeframe={timeframe} onChange={(next) => update(index, next)} onRemove={group.items.length > 1 ? () => remove(index) : undefined} />
        ) : (
          <ConditionRow key={index} condition={item} lead={index === 0 ? "If" : word} catalog={catalog} timeframe={timeframe} onChange={(next) => update(index, next)} onRemove={() => (group.items.length > 1 ? remove(index) : undefined)} />
        ),
      )}
      <div className="flex gap-2">
        <button type="button" disabled={group.items.length >= 20} className="rounded border border-dashed border-[#26303C] px-2 py-1 text-xs text-[#94A3B8] hover:text-[#E6EDF3] disabled:opacity-40" onClick={() => onChange({ ...group, items: [...group.items, NEW_CONDITION] })}>
          + Condition
        </button>
        {depth < 3 ? (
          <button type="button" className="rounded border border-dashed border-[#26303C] px-2 py-1 text-xs text-[#94A3B8] hover:text-[#E6EDF3]" onClick={() => onChange({ ...group, items: [...group.items, { logic: group.logic === "all" ? "any" : "all", items: [NEW_CONDITION] }] })}>
            + Group ({group.logic === "all" ? "OR" : "AND"} inside)
          </button>
        ) : null}
      </div>
    </div>
  );
}

// Kept for older imports: a flat list editor maps onto a single group.
export function ConditionList({ title, hint, conditions, onChange, catalog, timeframe = "1d" }: { title: string; hint: string; conditions: Condition[]; onChange: (next: Condition[]) => void; catalog: OperandInfo[]; minimum?: number; timeframe?: Timeframe }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="text-xs text-[#64748B]">{hint}</p>
      <GroupEditor group={{ logic: "all", items: conditions }} catalog={catalog} timeframe={timeframe} onChange={(next) => onChange(next.items.filter((item): item is Condition => !isGroup(item)))} />
    </div>
  );
}
