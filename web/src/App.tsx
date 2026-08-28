import { useEffect, useState } from "react";
import "./App.css";
import { fetchFuels } from "./api";
import { FuelSelect } from "./components/FuelSelect";
import { MapView } from "./components/MapView";
import { RadiusControl } from "./components/RadiusControl";
import { ResultsList } from "./components/ResultsList";
import { useDebouncedSearch } from "./hooks/useDebouncedSearch";
import type { FuelCode, FuelInfo, LatLon } from "./types";
import { formatPrice } from "./utils";

const DEFAULT_RADIUS_M = 5000;
const DEFAULT_FUEL: FuelCode = "gazole";
const MAX_RADIUS_M = 30000;

type SheetState = "collapsed" | "half" | "full";

function App() {
  const [point, setPoint] = useState<LatLon | null>(null);
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [fuel, setFuel] = useState<FuelCode>(DEFAULT_FUEL);
  const [fuels, setFuels] = useState<FuelInfo[]>([]);
  const [sort, setSort] = useState<"price" | "distance">("price");
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const [hoveredStationId, setHoveredStationId] = useState<number | null>(null);
  const [sheetState, setSheetState] = useState<SheetState>("half");

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

  const handleGeolocate = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setPoint({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => {},
      { timeout: 5000 },
    );
  };

  const cycleSheet = () => {
    setSheetState((s) => (s === "collapsed" ? "half" : s === "half" ? "full" : "collapsed"));
  };

  const handleSelectStation = (id: number) => {
    setSelectedStationId(id);
    setSheetState("half");
  };

  const cheapestPrice = data?.items?.length
    ? Math.min(...data.items.map((s) => s.price_eur).filter((p): p is number => p !== null))
    : null;

  return (
    <div className="app-shell">
      <MapView
        point={point}
        radiusM={radiusM}
        onPointChange={setPoint}
        stations={data?.items ?? []}
        selectedStationId={selectedStationId}
        hoveredStationId={hoveredStationId}
        onStationClick={handleSelectStation}
        onStationHover={setHoveredStationId}
      />

      <div className={`sidebar sheet-${sheetState}`}>
        <div className="sheet-handle" onClick={cycleSheet}>
          <div className="handle-bar" />
          <div className="sheet-peek">
            {point && data && cheapestPrice !== null ? (
              <>
                <strong>{data.total}</strong> station{data.total > 1 ? "s" : ""}
                {" — dès "}
                <strong>{formatPrice(cheapestPrice)}</strong>
              </>
            ) : point && loading ? (
              "Recherche…"
            ) : !point ? (
              "Cliquez sur la carte ou utilisez votre position"
            ) : (
              "Aucune station"
            )}
          </div>
        </div>

        <div className="sidebar-controls">
          <div className="controls-header">
            <h1>FuelNow</h1>
            <button className="btn-geolocate" onClick={handleGeolocate} aria-label="Ma position">
              📍
            </button>
          </div>
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
              selectedStationId={selectedStationId}
              radiusM={radiusM}
              sort={sort}
              onSortChange={setSort}
              onSelectStation={handleSelectStation}
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
