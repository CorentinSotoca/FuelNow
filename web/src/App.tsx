import { useEffect, useState } from "react";
import "./App.css";
import { fetchFuels } from "./api";
import { FuelSelect } from "./components/FuelSelect";
import { MapView } from "./components/MapView";
import { RadiusControl } from "./components/RadiusControl";
import { ResultsList } from "./components/ResultsList";
import { useDebouncedSearch } from "./hooks/useDebouncedSearch";
import type { FuelCode, FuelInfo, LatLon } from "./types";

const DEFAULT_RADIUS_M = 5000;
const DEFAULT_FUEL: FuelCode = "gazole";
const MAX_RADIUS_M = 30000;

function App() {
  const [point, setPoint] = useState<LatLon | null>(null);
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [fuel, setFuel] = useState<FuelCode>(DEFAULT_FUEL);
  const [fuels, setFuels] = useState<FuelInfo[]>([]);
  const [sort, setSort] = useState<"price" | "distance">("price");
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const [hoveredStationId, setHoveredStationId] = useState<number | null>(null);

  const { data, loading, error, retry } = useDebouncedSearch({
    point,
    radiusM,
    fuel,
    sort,
  });

  useEffect(() => {
    fetchFuels()
      .then(setFuels)
      .catch(() => {});
  }, []);

  const handleExpandRadius = (deltaM: number) => {
    setRadiusM((r) => Math.min(r + deltaM, MAX_RADIUS_M));
  };

  return (
    <div className="app-shell">
      <MapView
        point={point}
        radiusM={radiusM}
        onPointChange={setPoint}
        stations={data?.items ?? []}
        selectedStationId={selectedStationId}
        hoveredStationId={hoveredStationId}
        onStationClick={setSelectedStationId}
        onStationHover={setHoveredStationId}
      />

      <div className="sidebar">
        <div className="sidebar-controls">
          <h1>FuelNow</h1>
          {!point && <p className="hint">Cliquez sur la carte pour choisir un point de recherche.</p>}
          <FuelSelect fuels={fuels} selected={fuel} onChange={setFuel} />
          <RadiusControl radiusM={radiusM} onChange={setRadiusM} />
        </div>

        <div className="sidebar-results">
          {point && (
            <ResultsList
              data={data}
              loading={loading}
              error={error}
              searchPoint={point}
              selectedStationId={selectedStationId}
              radiusM={radiusM}
              sort={sort}
              onSortChange={setSort}
              onSelectStation={setSelectedStationId}
              onHoverStation={setHoveredStationId}
              onRetry={retry}
              onExpandRadius={handleExpandRadius}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
