import { useEffect, useState } from "react";
import "./App.css";
import { fetchFuels } from "./api";
import { FuelSelect } from "./components/FuelSelect";
import { MapView } from "./components/MapView";
import { RadiusControl } from "./components/RadiusControl";
import type { FuelCode, FuelInfo, LatLon } from "./types";

const DEFAULT_RADIUS_M = 5000;
const DEFAULT_FUEL: FuelCode = "gazole";

function App() {
  const [point, setPoint] = useState<LatLon | null>(null);
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [fuel, setFuel] = useState<FuelCode>(DEFAULT_FUEL);
  const [fuels, setFuels] = useState<FuelInfo[]>([]);

  useEffect(() => {
    fetchFuels()
      .then(setFuels)
      .catch(() => {
        /* select vide si l'API est indisponible ; géré en étape suivante */
      });
  }, []);

  return (
    <div className="app-shell">
      <MapView point={point} radiusM={radiusM} onPointChange={setPoint} />

      <div className="panel">
        <h1>FuelNow</h1>
        <p className="hint">Cliquez sur la carte pour choisir un point de recherche.</p>
        <FuelSelect fuels={fuels} selected={fuel} onChange={setFuel} />
        <RadiusControl radiusM={radiusM} onChange={setRadiusM} />
      </div>
    </div>
  );
}

export default App;
