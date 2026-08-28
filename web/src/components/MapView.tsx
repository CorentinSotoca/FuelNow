import { useEffect, useMemo, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  Popup,
  type GeoJSONSource,
  type MapLayerMouseEvent,
  type MapMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { LatLon, StationSearchItem } from "../types";
import { circleGeoJSON } from "../geo";
import { formatDistance, formatPrice, priceQuartiles, type Quartiles } from "../utils";

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
const STATION_SOURCE_ID = "station-markers";
const STATION_LAYER_ID = "station-markers";
const MARKER_ELEMENT_ID = "search-point-marker";

interface MapViewProps {
  point: LatLon | null;
  radiusM: number;
  onPointChange: (point: LatLon) => void;
  stations: StationSearchItem[];
  selectedStationId: number | null;
  hoveredStationId: number | null;
  onStationClick: (id: number) => void;
  onStationHover: (id: number | null) => void;
}

function stationsToGeoJSON(stations: StationSearchItem[]) {
  return {
    type: "FeatureCollection" as const,
    features: stations.map((s) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [s.lon, s.lat] },
      properties: {
        id: s.id,
        price: s.price_eur,
        address: s.address ?? "",
        city: s.city ?? "",
        distance_m: s.distance_m,
      },
    })),
  };
}

function buildColorExpression(q: Quartiles | null) {
  if (!q) return "#2563eb";
  const stops: (string | number)[] = [];
  let prev = -Infinity;
  for (const [val, color] of [
    [0, "#16a34a"],
    [q.q1, "#84cc16"],
    [q.q2, "#f59e0b"],
    [q.q3, "#dc2626"],
  ] as [number, string][]) {
    if (val > prev) {
      stops.push(val, color);
      prev = val;
    }
  }
  return [
    "step",
    ["coalesce", ["get", "price"], -1],
    "#9ca3af",
    ...stops,
  ] as unknown as string;
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
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const styleReadyRef = useRef(false);
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
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.15 },
      });
      map.addLayer({
        id: `${CIRCLE_SOURCE_ID}-line`,
        type: "line",
        source: CIRCLE_SOURCE_ID,
        paint: { "line-color": "#2563eb", "line-width": 2 },
      });

      map.addSource(STATION_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: STATION_LAYER_ID,
        type: "circle",
        source: STATION_SOURCE_ID,
        paint: {
          "circle-color": "#2563eb",
          "circle-radius": 6,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });

      styleReadyRef.current = true;
    });

    map.on("click", (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: [STATION_LAYER_ID] });
      if (features.length > 0) return;
      callbacksRef.current.onPointChange({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    });

    map.on("click", STATION_LAYER_ID, (e: MapLayerMouseEvent) => {
      const f = e.features?.[0];
      if (!f) return;
      const id = f.properties?.id as number;
      callbacksRef.current.onStationClick(id);

      const lat = (f.geometry as unknown as { coordinates: [number, number] }).coordinates[1];
      const lon = (f.geometry as unknown as { coordinates: [number, number] }).coordinates[0];
      const price = f.properties?.price as number | null;
      const address = f.properties?.address as string;
      const distance = f.properties?.distance_m as number;

      const html = `
        <div class="station-popup">
          <div class="station-popup-price">${formatPrice(price)}</div>
          ${address ? `<div class="station-popup-addr">${address}</div>` : ""}
          <div class="station-popup-dist">${formatDistance(distance)}</div>
        </div>`;
      popupRef.current?.remove();
      popupRef.current = new Popup({ closeButton: false, closeOnClick: true })
        .setLngLat([lon, lat])
        .setHTML(html)
        .addTo(map);
    });

    map.on("mouseenter", STATION_LAYER_ID, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mousemove", STATION_LAYER_ID, (e: MapLayerMouseEvent) => {
      const f = e.features?.[0];
      if (f) callbacksRef.current.onStationHover(f.properties?.id as number);
    });
    map.on("mouseleave", STATION_LAYER_ID, () => {
      map.getCanvas().style.cursor = "";
      callbacksRef.current.onStationHover(null);
    });

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          callbacksRef.current.onPointChange({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        },
        () => {},
        { timeout: 5000 },
      );
    }

    return () => {
      popupRef.current?.remove();
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
      el.id = MARKER_ELEMENT_ID;
      el.style.width = "18px";
      el.style.height = "18px";
      el.style.borderRadius = "50%";
      el.style.background = "#dc2626";
      el.style.border = "2px solid white";
      el.style.boxShadow = "0 0 4px rgba(0,0,0,0.4)";
      el.style.cursor = "grab";

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

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const setStations = () => {
      const source = map.getSource(STATION_SOURCE_ID) as GeoJSONSource | undefined;
      if (!source) return;
      source.setData(stationsToGeoJSON(stations));
    };

    if (styleReadyRef.current) {
      setStations();
    } else {
      map.once("load", setStations);
    }
  }, [stations]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current) return;
    if (!map.getLayer(STATION_LAYER_ID)) return;

    map.setPaintProperty(STATION_LAYER_ID, "circle-color", buildColorExpression(quartiles));
  }, [quartiles]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReadyRef.current) return;
    if (!map.getLayer(STATION_LAYER_ID)) return;

    const sel = selectedStationId ?? -1;
    const hov = hoveredStationId ?? -1;

    map.setPaintProperty(STATION_LAYER_ID, "circle-radius", [
      "case",
      ["==", ["get", "id"], sel], 9,
      ["==", ["get", "id"], hov], 7,
      5,
    ]);
    map.setPaintProperty(STATION_LAYER_ID, "circle-stroke-width", [
      "case",
      ["==", ["get", "id"], sel], 3,
      1.5,
    ]);
  }, [selectedStationId, hoveredStationId]);

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
          ${station.address ? `<div class="station-popup-addr">${station.address}</div>` : ""}
          <div class="station-popup-dist">${formatDistance(station.distance_m)}</div>
        </div>`)
      .addTo(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStationId]);

  return <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />;
}
