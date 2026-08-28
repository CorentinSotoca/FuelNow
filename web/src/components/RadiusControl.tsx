interface RadiusControlProps {
  radiusM: number;
  onChange: (radiusM: number) => void;
}

const MIN_M = 500;
const MAX_M = 30000;
const STEP_M = 500;

export function RadiusControl({ radiusM, onChange }: RadiusControlProps) {
  const km = (radiusM / 1000).toFixed(1);

  return (
    <div className="radius-control">
      <label htmlFor="radius-slider">Rayon : {km} km</label>
      <input
        id="radius-slider"
        type="range"
        min={MIN_M}
        max={MAX_M}
        step={STEP_M}
        value={radiusM}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
