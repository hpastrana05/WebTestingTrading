"use client";

import { IndicatorCatalog, IndicatorInfo, Operand, RuleNode } from "@/lib/api";

type Props = {
  title: string;
  group: RuleNode;
  catalog: IndicatorCatalog;
  onChange: (next: RuleNode) => void;
};

function defaultParams(indicator: IndicatorInfo): Record<string, number> {
  const params: Record<string, number> = {};
  indicator.params.forEach((p) => {
    params[p.name] = p.default;
  });
  return params;
}

function defaultOperand(kind: Operand["kind"], catalog: IndicatorCatalog): Operand {
  if (kind === "price") {
    return { kind: "price", field: "Close" };
  }
  if (kind === "value") {
    return { kind: "value", value: 0 };
  }
  const first = catalog.indicators[0];
  return {
    kind: "indicator",
    indicator: first?.id || "sma",
    params: first ? defaultParams(first) : { length: 20 },
    output: first?.outputs[0]?.id || "SMA",
  };
}

export function emptyCondition(catalog: IndicatorCatalog): RuleNode {
  return {
    type: "condition",
    left: defaultOperand("indicator", catalog),
    operator: ">",
    right: defaultOperand("value", catalog),
  };
}

export function emptyGroup(logic: "all" | "any" = "all"): RuleNode {
  return { type: "group", logic, children: [] };
}

function OperandEditor({
  operand,
  catalog,
  onChange,
}: {
  operand: Operand;
  catalog: IndicatorCatalog;
  onChange: (next: Operand) => void;
}) {
  const indicator = catalog.indicators.find((i) => i.id === operand.indicator);

  return (
    <div className="operand">
      <select
        value={operand.kind}
        onChange={(e) =>
          onChange(defaultOperand(e.target.value as Operand["kind"], catalog))
        }
      >
        <option value="indicator">Indicator</option>
        <option value="price">Price</option>
        <option value="value">Value</option>
      </select>

      {operand.kind === "price" && (
        <select
          value={operand.field || "Close"}
          onChange={(e) => onChange({ ...operand, field: e.target.value })}
        >
          {catalog.price_fields.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label}
            </option>
          ))}
        </select>
      )}

      {operand.kind === "value" && (
        <input
          type="number"
          step="any"
          value={operand.value ?? 0}
          onChange={(e) => onChange({ ...operand, value: Number(e.target.value) })}
        />
      )}

      {operand.kind === "indicator" && (
        <>
          <select
            value={operand.indicator || ""}
            onChange={(e) => {
              const next = catalog.indicators.find((i) => i.id === e.target.value);
              if (!next) return;
              onChange({
                kind: "indicator",
                indicator: next.id,
                params: defaultParams(next),
                output: next.outputs[0]?.id,
              });
            }}
          >
            <option value="" disabled>
              Select signal logic...
            </option>
            {catalog.indicators.map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
              </option>
            ))}
          </select>

          {indicator && indicator.outputs.length > 1 && (
            <select
              value={operand.output || indicator.outputs[0].id}
              onChange={(e) => onChange({ ...operand, output: e.target.value })}
            >
              {indicator.outputs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          )}

          {indicator?.params.map((p) => (
            <label key={p.name} className="param-inline">
              <span>{p.name}</span>
              <input
                type="number"
                step={p.step ?? 1}
                min={p.min}
                max={p.max}
                value={operand.params?.[p.name] ?? p.default}
                onChange={(e) =>
                  onChange({
                    ...operand,
                    params: {
                      ...(operand.params || {}),
                      [p.name]: Number(e.target.value),
                    },
                  })
                }
              />
            </label>
          ))}
        </>
      )}
    </div>
  );
}

function ConditionRow({
  node,
  catalog,
  onChange,
  onRemove,
}: {
  node: RuleNode;
  catalog: IndicatorCatalog;
  onChange: (next: RuleNode) => void;
  onRemove: () => void;
}) {
  return (
    <div className="rule-row">
      <OperandEditor
        operand={node.left || defaultOperand("indicator", catalog)}
        catalog={catalog}
        onChange={(left) => onChange({ ...node, left })}
      />
      <select
        className="operator"
        value={node.operator || ">"}
        onChange={(e) => onChange({ ...node, operator: e.target.value })}
      >
        {catalog.operators.map((op) => (
          <option key={op.id} value={op.id}>
            {op.label}
          </option>
        ))}
      </select>
      <OperandEditor
        operand={node.right || defaultOperand("value", catalog)}
        catalog={catalog}
        onChange={(right) => onChange({ ...node, right })}
      />
      <button type="button" className="icon-btn" onClick={onRemove} aria-label="Remove">
        ×
      </button>
    </div>
  );
}

function GroupEditor({
  group,
  catalog,
  onChange,
  nested = false,
}: {
  group: RuleNode;
  catalog: IndicatorCatalog;
  onChange: (next: RuleNode) => void;
  nested?: boolean;
}) {
  const children = group.children || [];

  function updateChild(index: number, next: RuleNode) {
    const copy = [...children];
    copy[index] = next;
    onChange({ ...group, children: copy });
  }

  function removeChild(index: number) {
    onChange({ ...group, children: children.filter((_, i) => i !== index) });
  }

  return (
    <div className={`rule-group ${nested ? "nested" : ""}`}>
      <div className="rule-group-head">
        <label>
          {nested ? "Group logic" : "Root logic"}
          <select
            value={group.logic || "all"}
            onChange={(e) =>
              onChange({ ...group, logic: e.target.value as "all" | "any" })
            }
          >
            <option value="all">ALL (AND)</option>
            <option value="any">ANY (OR)</option>
          </select>
        </label>
        <div className="row" style={{ flex: "0 0 auto" }}>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              onChange({ ...group, children: [...children, emptyCondition(catalog)] })
            }
          >
            + Add Signal
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              onChange({
                ...group,
                children: [...children, emptyGroup(group.logic || "all")],
              })
            }
          >
            + Add Group
          </button>
        </div>
      </div>

      {children.length === 0 && (
        <p className="muted">No signals yet. Add a signal or nested group.</p>
      )}

      <div className="stack">
        {children.map((child, index) =>
          child.type === "group" ? (
            <div key={index} className="nested-wrap">
              <div className="nested-toolbar">
                <strong>Nested group</strong>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => removeChild(index)}
                  aria-label="Remove group"
                >
                  ×
                </button>
              </div>
              <GroupEditor
                group={child}
                catalog={catalog}
                nested
                onChange={(next) => updateChild(index, next)}
              />
            </div>
          ) : (
            <ConditionRow
              key={index}
              node={child}
              catalog={catalog}
              onChange={(next) => updateChild(index, next)}
              onRemove={() => removeChild(index)}
            />
          )
        )}
      </div>
    </div>
  );
}

export default function RuleBuilder({ title, group, catalog, onChange }: Props) {
  return (
    <section className="panel stack">
      <h2>{title}</h2>
      <p className="muted">
        Each signal computes its own indicators from OHLCV via pandas-ta. Nest groups for
        complex AND/OR logic.
      </p>
      <GroupEditor group={group} catalog={catalog} onChange={onChange} />
    </section>
  );
}
