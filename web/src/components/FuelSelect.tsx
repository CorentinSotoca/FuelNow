import type { FuelCode, FuelInfo } from "../types";

interface FuelSelectProps {
  fuels: FuelInfo[];
  selected: FuelCode;
  onChange: (fuel: FuelCode) => void;
}

export function FuelSelect({ fuels, selected, onChange }: FuelSelectProps) {
  return (
    <div className="fuel-select" role="radiogroup" aria-label="Carburant">
      {fuels.map((f) => (
        <button
          key={f.code}
          type="button"
          className={f.code === selected ? "fuel-option selected" : "fuel-option"}
          aria-pressed={f.code === selected}
          onClick={() => onChange(f.code)}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
