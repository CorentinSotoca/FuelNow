import type { Feature, Polygon } from "geojson";
import type { LatLon } from "./types";

/**
 * Génère un polygone GeoJSON approximant un cercle de rayon `radiusM` mètres
 * autour du point `center`, sans dépendance externe (évite turf.js).
 */
export function circleGeoJSON(center: LatLon, radiusM: number, points = 64): Feature<Polygon> {
  const coords: [number, number][] = [];
  const earthRadius = 6371000;
  const latRad = (center.lat * Math.PI) / 180;

  for (let i = 0; i <= points; i++) {
    const angle = (i / points) * 2 * Math.PI;
    const dLat = (radiusM * Math.cos(angle)) / earthRadius;
    const dLon = (radiusM * Math.sin(angle)) / (earthRadius * Math.cos(latRad));
    const lat = center.lat + (dLat * 180) / Math.PI;
    const lon = center.lon + (dLon * 180) / Math.PI;
    coords.push([lon, lat]);
  }

  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      coordinates: [coords],
    },
  };
}
