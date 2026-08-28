import { useEffect, useRef } from "react";
import {
  Map as MapLibreMap,
  Marker,
  type GeoJSONSource,
  type MapMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { LatLon } from "../types";
import { circleGeoJSON } from "../geo";

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
const MARKER_ELEMENT_ID = "search-point-marker";

interface MapViewProps {
  point: LatLon | null;
  radiusM: number;
  onPointChange: (point: LatLon) => void;
}

export function MapView({ point, radiusM, onPointChange }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const styleReadyRef = useRef(false);

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
      styleReadyRef.current = true;
    });

    map.on("click", (e: MapMouseEvent) => {
      onPointChange({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    });

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          onPointChange({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        },
        () => {
          /* refus ou indisponible : on garde le centre France */
        },
        { timeout: 5000 },
      );
    }

    return () => {
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
        onPointChange({ lat: pos.lat, lon: pos.lng });
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

  return <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />;
}
