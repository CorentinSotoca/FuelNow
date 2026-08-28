import type { BeMaxPriceResponse, FuelCode, FuelInfo, LatLon, StationSearchResponse } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function fetchFuels(): Promise<FuelInfo[]> {
  const res = await fetch("/api/fuels");
  if (!res.ok) throw new ApiError(res.status, `Failed to load fuels: ${res.status}`);
  return res.json();
}

export interface SearchParams {
  point: LatLon;
  radiusM: number;
  fuel: FuelCode;
  includeUnpriced?: boolean;
  includeOutage?: boolean;
  sort?: "price" | "distance";
  page?: number;
  pageSize?: number;
}

export async function searchStations(params: SearchParams): Promise<StationSearchResponse> {
  const qs = new URLSearchParams({
    lat: String(params.point.lat),
    lon: String(params.point.lon),
    radius_m: String(Math.round(params.radiusM)),
    fuel: params.fuel,
    include_unpriced: String(params.includeUnpriced ?? false),
    include_outage: String(params.includeOutage ?? false),
    sort: params.sort ?? "price",
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 25),
  });

  const res = await fetch(`/api/stations/search?${qs.toString()}`);
  if (res.status === 429) {
    throw new ApiError(429, "Trop de requêtes, veuillez patienter quelques instants.");
  }
  if (res.status === 422) {
    throw new ApiError(422, "Paramètres de recherche invalides.");
  }
  if (!res.ok) {
    throw new ApiError(res.status, `Erreur serveur (${res.status})`);
  }
  return res.json();
}

export async function fetchBePrices(fuel?: string): Promise<BeMaxPriceResponse> {
  const qs = new URLSearchParams();
  if (fuel) qs.set("fuel", fuel);
  const res = await fetch(`/api/be/prices?${qs.toString()}`);
  if (!res.ok) throw new ApiError(res.status, `Failed to load BE prices: ${res.status}`);
  return res.json();
}
