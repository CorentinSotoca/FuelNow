import { useEffect, useMemo, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  Popup,
  setWorkerUrl,
  type GeoJSONSource,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { GpsState } from "../App";
import type { LatLon, StationSearchItem } from "../types";
import { circleGeoJSON } from "../geo";
import { formatDistance, formatPrice, priceQuartiles, quartileColor } from "../utils";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

setWorkerUrl(workerUrl);

const FRANCE_CENTER: LatLon = { lat: 46.6, lon: 2.5 };
const FRANCE_ZOOM = 5.3;

const OSM_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const CIRCLE_SOURCE_ID = "search-radius";
const GPS_ACCURACY_SOURCE_ID = "gps-accuracy";

interface MapViewProps {
  point: LatLon | null;
  radiusM: number;
  onPointChange: (point: LatLon) => void;
  stations: StationSearchItem[];
  selectedStationId: number | null;
  hoveredStationId: number | null;
  onStationClick: (id: number) => void;
  onStationHover: (id: number | null) => void;
  gps: GpsState | null;
  gpsTracking: boolean;
  onToggleGpsTracking: () => void;
  onSyncToGps: () => void;
}

function formatPriceLabel(price: number | null): string {
  if (price === null) return "—";
  return price.toFixed(3).replace(".", ",");
}

function applyStationElStyle(
  el: HTMLElement,
  station: StationSearchItem,
  color: string,
  selected: boolean,
  hovered: boolean,
) {
  el.textContent = formatPriceLabel(station.price_eur);
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.borderRadius = "999px";
  el.style.fontFamily = "system-ui, sans-serif";
  el.style.fontWeight = "700";
  el.style.color = "white";
  el.style.background = color;
  el.style.border = "2px solid white";
  el.style.boxShadow = "0 1px 4px rgba(0,0,0,0.35)";
  el.style.cursor = "pointer";
  el.style.fontSize = `${selected ? 13 : hovered ? 12 : 11}px`;
  el.style.minWidth = `${selected ? 42 : hovered ? 38 : 34}px`;
  el.style.height = `${selected ? 28 : hovered ? 25 : 22}px`;
  el.style.padding = "0 6px";
  el.style.whiteSpace = "nowrap";
  el.style.zIndex = selected ? "1000" : "";
}

export function MapView({
  point,
  radiusM,
  onPointChange,
  stations,
  selectedStationId,
  hoveredStationId,
  onStationClick,
  onStationHover,
  gps,
  gpsTracking,
  onToggleGpsTracking,
  onSyncToGps,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const gpsMarkerRef = useRef<Marker | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const styleReadyRef = useRef(false);
  const stationMarkersRef = useRef<Map<number, Marker>>(new Map());
  const callbacksRef = useRef({ onPointChange, onStationClick, onStationHover });
  callbacksRef.current = { onPointChange, onStationClick, onStationHover };

  const quartiles = useMemo(() => priceQuartiles(stations), [stations]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new MapLibreMap({
      container: containerRef.current,
      style: OSM_STYLE,
      center: [FRANCE_CENTER.lon, FRANCE_CENTER.lat],
      zoom: FRANCE_ZOOM,
    });
    mapRef.current = map;

    map.on("load", () => {
      map.addSource(CIRCLE_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: `${CIRCLE_SOURCE_ID}-fill`,
        type: "fill",
        source: CIRCLE_SOURCE_ID,
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.18 },
      });
      map.addLayer({
        id: `${CIRCLE_SOURCE_ID}-line`,
        type: "line",
        source: CIRCLE_SOURCE_ID,
        paint: { "line-color": "#2563eb", "line-width": 3, "line-dasharray": [3, 2] },
      });

      map.addSource(GPS_ACCURACY_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: `${GPS_ACCURACY_SOURCE_ID}-fill`,
        type: "fill",
        source: GPS_ACCURACY_SOURCE_ID,
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.12 },
      });

      styleReadyRef.current = true;
    });

    map.on("click", (e) => {
      callbacksRef.current.onPointChange({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    });

    return () => {
      popupRef.current?.remove();
      stationMarkersRef.current.forEach((m) => m.remove());
      stationMarkersRef.current.clear();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !point) return;

    if (!markerRef.current) {
      const el = document.createElement("div");
      el.style.cssText = `
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #dc2626;
        border: 2px solid white;
        box-shadow: 0 0 4px rgba(0,0,0,0.4);
        cursor: grab;
      `;

      const marker = new Marker({ element: el, draggable: true })
        .setLngLat([point.lon, point.lat])
        .addTo(map);

      marker.on("dragend", () => {
        const pos = marker.getLngLat();
        callbacksRef.current.onPointChange({ lat: pos.lat, lon: pos.lng });
      });

      markerRef.current = marker;
    } else {
      markerRef.current.setLngLat([point.lon, point.lat]);
    }

    map.flyTo({ center: [point.lon, point.lat], zoom: Math.max(map.getZoom(), 11) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [point?.lat, point?.lon]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !point) return;

    const setCircle = () => {
      const source = map.getSource(CIRCLE_SOURCE_ID) as GeoJSONSource | undefined;
      if (!source) return;
      source.setData({
        type: "FeatureCollection",
        features: [circleGeoJSON(point, radiusM)],
      });
    };

    if (styleReadyRef.current) {
      setCircle();
    } else {
      map.once("load", setCircle);
    }
  }, [point?.lat, point?.lon, radiusM]);

  // GPS blue dot marker + accuracy halo
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const updateGps = () => {
      if (!gps) {
        if (gpsMarkerRef.current) {
          gpsMarkerRef.current.remove();
          gpsMarkerRef.current = null;
        }
        const src = map.getSource(GPS_ACCURACY_SOURCE_ID) as GeoJSONSource | undefined;
        if (src) {
          src.setData({ type: "FeatureCollection", features: [] });
        }
        return;
      }

      const { position, accuracy } = gps;

      if (!gpsMarkerRef.current) {
        const el = document.createElement("div");
        el.className = "gps-dot";
        const marker = new Marker({ element: el })
          .setLngLat([position.lon, position.lat])
          .addTo(map);
        gpsMarkerRef.current = marker;
      } else {
        gpsMarkerRef.current.setLngLat([position.lon, position.lat]);
      }

      const src = map.getSource(GPS_ACCURACY_SOURCE_ID) as GeoJSONSource | undefined;
      if (src) {
        src.setData({
          type: "FeatureCollection",
          features: [circleGeoJSON(position, accuracy)],
        });
      }

      if (gpsTracking) {
        map.easeTo({ center: [position.lon, position.lat] });
      }
    };

    if (styleReadyRef.current) {
      updateGps();
    } else {
      map.once("load", updateGps);
    }
  }, [gps?.position.lat, gps?.position.lon, gps?.accuracy, gpsTracking]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const syncMarkers = () => {
      const existing = stationMarkersRef.current;
      const incomingIds = new Set(stations.map((s) => s.id));

      existing.forEach((marker, id) => {
        if (!incomingIds.has(id)) {
          marker.remove();
          existing.delete(id);
        }
      });

      for (const station of stations) {
        const color = quartileColor(station.price_eur, quartiles);
        const isSel = station.id === selectedStationId;
        const isHov = station.id === hoveredStationId;
        const existingMarker = existing.get(station.id);

        if (existingMarker) {
          const el = existingMarker.getElement() as HTMLElement;
          applyStationElStyle(el, station, color, isSel, isHov);
        } else {
          const el = document.createElement("div");
          applyStationElStyle(el, station, color, isSel, isHov);
          el.addEventListener("click", (ev) => {
            ev.stopPropagation();
            callbacksRef.current.onStationClick(station.id);
          });
          el.addEventListener("mouseenter", () => {
            callbacksRef.current.onStationHover(station.id);
          });
          el.addEventListener("mouseleave", () => {
            callbacksRef.current.onStationHover(null);
          });

          const marker = new Marker({ element: el })
            .setLngLat([station.lon, station.lat])
            .addTo(map);
          existing.set(station.id, marker);
        }
      }
    };

    if (styleReadyRef.current) {
      syncMarkers();
    } else {
      map.once("load", syncMarkers);
    }
  }, [stations, quartiles, selectedStationId, hoveredStationId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || selectedStationId === null) return;

    const station = stations.find((s) => s.id === selectedStationId);
    if (!station) return;

    map.flyTo({
      center: [station.lon, station.lat],
      zoom: Math.max(map.getZoom(), 13),
    });

    popupRef.current?.remove();
    popupRef.current = new Popup({ closeButton: false, closeOnClick: true })
      .setLngLat([station.lon, station.lat])
      .setHTML(`
        <div class="station-popup">
          <div class="station-popup-price">${formatPrice(station.price_eur)}</div>
          ${station.address || station.postal_code || station.city ? `<div class="station-popup-addr">${[station.address, [station.postal_code, station.city].filter(Boolean).join(" ")].filter(Boolean).join("<br>")}</div>` : ""}
          <div class="station-popup-dist">${formatDistance(station.distance_m)}</div>
        </div>`)
      .addTo(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStationId]);

  return (
    <>
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />
      <div className="map-controls">
        <button
          className={`map-btn ${gpsTracking ? "map-btn-active" : ""}`}
          onClick={onToggleGpsTracking}
          aria-label={gpsTracking ? "Arrêter le suivi GPS" : "Activer le suivi GPS"}
        >
          {gpsTracking ? "🔵" : "📍"}
        </button>
        {gps && gpsTracking && (
          <button
            className="map-btn"
            onClick={onSyncToGps}
            aria-label="Rechercher autour de moi"
          >
            🎯
          </button>
        )}
      </div>
    </>
  );
}
