import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import { fetchFuels } from "./api";
import { BeMaxPricePanel } from "./components/BeMaxPricePanel";
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
const SAVED_POINT_KEY = "fuelnow:lastPosition";
const GPS_OPT_OUT_KEY = "fuelnow:gpsOptOut";

export type GpsState = {
  position: LatLon;
  accuracy: number;
  heading: number | null;
};

type SheetState = "collapsed" | "half" | "full";

const SHEET_HEIGHTS: Record<SheetState, number> = {
  collapsed: 56,
  half: 0.5,
  full: 0.88,
};

function sheetToPx(state: SheetState): number {
  if (state === "collapsed") return SHEET_HEIGHTS.collapsed;
  return Math.round(window.innerHeight * SHEET_HEIGHTS[state]);
}

function pxToSheet(px: number): SheetState {
  const collapsed = SHEET_HEIGHTS.collapsed;
  const half = Math.round(window.innerHeight * 0.5);
  const full = Math.round(window.innerHeight * 0.88);
  const diffs: [SheetState, number][] = [
    ["collapsed", Math.abs(px - collapsed)],
    ["half", Math.abs(px - half)],
    ["full", Math.abs(px - full)],
  ];
  diffs.sort((a, b) => a[1] - b[1]);
  return diffs[0][0];
}

function useOnlineStatus() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

function App() {
  const [point, setPoint] = useState<LatLon | null>(() => {
    try {
      const saved = localStorage.getItem(SAVED_POINT_KEY);
      if (saved) return JSON.parse(saved) as LatLon;
    } catch {}
    return null;
  });
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [fuel, setFuel] = useState<FuelCode>(DEFAULT_FUEL);
  const [fuels, setFuels] = useState<FuelInfo[]>([]);
  const [sort, setSort] = useState<"price" | "distance">("price");
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const [hoveredStationId, setHoveredStationId] = useState<number | null>(null);
  const [sheetState, setSheetState] = useState<SheetState>("half");
  const [gpsTracking, setGpsTracking] = useState(() => {
    try {
      return localStorage.getItem(GPS_OPT_OUT_KEY) !== "1";
    } catch {}
    return true;
  });
  const [gps, setGps] = useState<GpsState | null>(null);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const online = useOnlineStatus();

  const sidebarRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startY: number; startHeight: number } | null>(null);
  const watchIdRef = useRef<number | null>(null);

  const { data, loading, error, retry, inBelgium, bePrices, beLoading } = useDebouncedSearch({
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

  useEffect(() => {
    if (point) {
      try {
        localStorage.setItem(SAVED_POINT_KEY, JSON.stringify(point));
      } catch {}
    }
  }, [point?.lat, point?.lon]);

  useEffect(() => {
    if (!gpsTracking) {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
      return;
    }

    if (!navigator.geolocation) {
      setGpsTracking(false);
      setGpsError("Géolocalisation non supportée par ce navigateur");
      return;
    }

    setGpsError(null);

    if (navigator.permissions) {
      navigator.permissions.query({ name: "geolocation" as PermissionName }).then((result) => {
        if (result.state === "denied") {
          setGpsError(
            "Localisation bloquée. Autorisez-la dans les réglages du navigateur (icône 🔒 dans la barre d'adresse → Autoriser la localisation).",
          );
          setGpsTracking(false);
          try { localStorage.setItem(GPS_OPT_OUT_KEY, "1"); } catch {}
        }
      }).catch(() => {});
    }

    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setGpsError(null);
        setGps({
          position: { lat: pos.coords.latitude, lon: pos.coords.longitude },
          accuracy: pos.coords.accuracy,
          heading: pos.coords.heading,
        });
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setGpsError(
            "Localisation bloquée. Autorisez-la dans les réglages du navigateur (icône 🔒 dans la barre d'adresse → Autoriser la localisation).",
          );
          try { localStorage.setItem(GPS_OPT_OUT_KEY, "1"); } catch {}
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          setGpsError("Position GPS indisponible. Vérifiez que le GPS de votre appareil est activé.");
        } else if (err.code === err.TIMEOUT) {
          setGpsError("Délai d'attente GPS dépassé. Réessayez à l'extérieur ou vérifiez votre signal GPS.");
        } else {
          setGpsError("Erreur de géolocalisation.");
        }
        setGpsTracking(false);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 },
    );

    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
  }, [gpsTracking]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden && watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      } else if (!document.hidden && gpsTracking && watchIdRef.current === null) {
        watchIdRef.current = navigator.geolocation.watchPosition(
          (pos) => {
            setGpsError(null);
            setGps({
              position: { lat: pos.coords.latitude, lon: pos.coords.longitude },
              accuracy: pos.coords.accuracy,
              heading: pos.coords.heading,
            });
          },
          (err) => {
            if (err.code === err.PERMISSION_DENIED) {
              setGpsError(
                "Localisation bloquée. Autorisez-la dans les réglages du navigateur (icône 🔒 dans la barre d'adresse → Autoriser la localisation).",
              );
            } else if (err.code === err.POSITION_UNAVAILABLE) {
              setGpsError("Position GPS indisponible. Vérifiez que le GPS de votre appareil est activé.");
            } else if (err.code === err.TIMEOUT) {
              setGpsError("Délai d'attente GPS dépassé. Réessayez à l'extérieur ou vérifiez votre signal GPS.");
            } else {
              setGpsError("Erreur de géolocalisation.");
            }
            setGpsTracking(false);
          },
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 },
        );
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [gpsTracking]);

  const handleExpandRadius = (deltaM: number) => {
    setRadiusM((r) => Math.min(r + deltaM, MAX_RADIUS_M));
  };

  const toggleGpsTracking = useCallback(() => {
    setGpsTracking((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(GPS_OPT_OUT_KEY, next ? "0" : "1");
      } catch {}
      if (next) setGpsError(null);
      return next;
    });
  }, []);

  const syncToGps = useCallback(() => {
    if (gps) setPoint(gps.position);
  }, [gps]);

  const handleTouchStart = (e: React.TouchEvent) => {
    dragRef.current = {
      startY: e.touches[0].clientY,
      startHeight: sidebarRef.current?.offsetHeight ?? sheetToPx(sheetState),
    };
    if (sidebarRef.current) {
      sidebarRef.current.style.transition = "none";
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!dragRef.current || !sidebarRef.current) return;
    const delta = dragRef.current.startY - e.touches[0].clientY;
    const newHeight = Math.max(
      SHEET_HEIGHTS.collapsed,
      Math.min(dragRef.current.startHeight + delta, window.innerHeight * 0.9),
    );
    sidebarRef.current.style.maxHeight = `${newHeight}px`;
  };

  const handleTouchEnd = () => {
    if (!dragRef.current || !sidebarRef.current) return;
    const currentHeight = sidebarRef.current.offsetHeight;
    sidebarRef.current.style.transition = "";
    sidebarRef.current.style.maxHeight = "";
    setSheetState(pxToSheet(currentHeight));
    dragRef.current = null;
  };

  const cycleSheet = () => {
    if (dragRef.current) return;
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
        gps={gps}
        gpsTracking={gpsTracking}
        gpsError={gpsError}
        onToggleGpsTracking={toggleGpsTracking}
        onSyncToGps={syncToGps}
      />

      <div
        ref={sidebarRef}
        className={`sidebar sheet-${sheetState}`}
      >
        <div
          className="sheet-handle"
          onClick={cycleSheet}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          <div className="handle-bar" />
          <div className="sheet-peek">
            {point && inBelgium && bePrices && bePrices.prices.length > 0 ? (
              (() => {
                const bePrice = bePrices.prices.find((p) => p.fuel_code === fuel);
                if (bePrice) {
                  return <>🇧🇪 Prix max : <strong>{formatPrice(bePrice.price_eur)}</strong></>;
                }
                return <>🇧🇪 Prix max non disponible pour ce carburant</>;
              })()
            ) : point && data && cheapestPrice !== null ? (
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
          </div>
          {!point && <p className="hint">Cliquez sur la carte pour choisir un point de recherche.</p>}
          <FuelSelect fuels={fuels} selected={fuel} onChange={setFuel} />
          <RadiusControl radiusM={radiusM} onChange={setRadiusM} />
        </div>

        <div className="sidebar-results">
          {!online && (
            <div className="offline-banner">Mode hors-ligne — données potentiellement anciennes</div>
          )}
          {point && inBelgium && (
            <BeMaxPricePanel bePrices={bePrices} loading={beLoading} fuel={fuel} />
          )}
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
              inBelgium={inBelgium}
            />
          )}
        </div>

        <div className="sidebar-footer">
          <a href="https://github.com/CorentinSotoca/FuelNow" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </div>
      </div>
    </div>
  );
}

export default App;
