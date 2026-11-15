import type { StationSearchItem } from "./types";

export interface Quartiles {
  q1: number;
  q2: number;
  q3: number;
}

export function priceQuartiles(items: StationSearchItem[]): Quartiles | null {
  const prices = items
    .map((i) => i.price_eur)
    .filter((p): p is number => p !== null)
    .sort((a, b) => a - b);
  if (prices.length < 4) return null;
  const at = (frac: number) => prices[Math.min(Math.floor(frac * prices.length), prices.length - 1)];
  return { q1: at(0.25), q2: at(0.5), q3: at(0.75) };
}

export function quartileColor(price: number | null, q: Quartiles | null): string {
  if (price === null) return "#9ca3af";
  if (!q) return "#2563eb";
  if (price <= q.q1) return "#16a34a";
  if (price <= q.q2) return "#84cc16";
  if (price <= q.q3) return "#f59e0b";
  return "#dc2626";
}

export function formatDistance(m: number): string {
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

export function formatHoursAgo(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Math.max(0, Date.now() - then);
  const h = Math.floor(diffMs / 3_600_000);
  if (h < 1) {
    const min = Math.floor(diffMs / 60_000);
    return min <= 1 ? "à l'instant" : `il y a ${min} min`;
  }
  if (h < 24) return `il y a ${h} h`;
  const d = Math.floor(h / 24);
  return `il y a ${d} j`;
}

export function formatPrice(price: number | null): string {
  if (price === null) return "—";
  return `${price.toFixed(3).replace(".", ",")} €`;
}

export function formatDelta(delta: number | null): string {
  if (delta === null || delta === 0) return "moins cher";
  return `+${delta.toFixed(3).replace(".", ",")} €`;
}

/**
 * Titre d'une station : l'enseigne OSM (brand), le nom, ou les deux
 * combinés quand le nom ne contient pas déjà l'enseigne.
 */
export function stationTitle(station: Pick<StationSearchItem, "brand" | "osm_name">): string {
  const brand = station.brand?.trim();
  const name = station.osm_name?.trim();
  if (brand && name && !name.toLowerCase().includes(brand.toLowerCase())) {
    return `${brand} – ${name}`;
  }
  return name || brand || "";
}

export interface StationNavLinks {
  waze: string;
  maps: string;
}

/**
 * Liens de navigation vers l'enseigne (le POI Maps/Waze de la station),
 * pas un simple pin posé sur l'adresse.
 *
 * - Google Maps : requête texte « enseigne, adresse, cp ville » → ouvre la
 *   fiche de l'établissement (son propre place card). Sans enseigne, on
 *   retombe sur les coordonnées.
 * - Waze : `q=enseigne ville` borné par `ll=lat,lon` → Waze résout le POI
 *   nommé près de la station et y navigue.
 */
export function stationNavLinks(station: StationSearchItem): StationNavLinks {
  const title = stationTitle(station);
  const cityLine = [station.postal_code, station.city].filter(Boolean).join(" ");
  const fullQuery = [title, station.address, cityLine].filter(Boolean).join(", ");

  const mapsQuery = title ? encodeURIComponent(fullQuery) : `${station.lat},${station.lon}`;
  const wazeParams = title
    ? `q=${encodeURIComponent(`${title} ${station.city ?? ""}`.trim())}&ll=${station.lat},${station.lon}`
    : `ll=${station.lat},${station.lon}`;

  return {
    waze: `https://waze.com/ul?${wazeParams}&navigate=yes`,
    maps: `https://www.google.com/maps/search/?api=1&query=${mapsQuery}`,
  };
}

const BELGIUM_BUFFER_POLYGON: [number, number][] = [
  [51.55, 2.35],
  [51.55, 6.30],
  [51.44, 6.26],
  [50.93, 6.21],
  [50.33, 6.58],
  [49.33, 6.00],
  [49.33, 5.28],
  [49.34, 4.31],
  [49.60, 3.80],
  [50.10, 3.80],
  [50.28, 3.97],
  [50.36, 3.45],
  [50.60, 2.95],
  [50.85, 2.45],
  [50.95, 2.10],
];

export function isNearBelgium(lat: number, lon: number): boolean {
  const n = BELGIUM_BUFFER_POLYGON.length;
  let inside = false;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const [yi, xi] = BELGIUM_BUFFER_POLYGON[i];
    const [yj, xj] = BELGIUM_BUFFER_POLYGON[j];
    if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

export function formatBeDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("fr-BE", { day: "2-digit", month: "2-digit", year: "numeric" });
}
