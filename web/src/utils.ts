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
  const diffMs = Date.now() - then;
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

export function isNearBelgium(lat: number, lon: number): boolean {
  return lat >= 49.3 && lat <= 51.7 && lon >= 2.2 && lon <= 6.8;
}

export function formatBeDate(dateStr: string): string {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("fr-BE", { day: "2-digit", month: "2-digit", year: "numeric" });
}
