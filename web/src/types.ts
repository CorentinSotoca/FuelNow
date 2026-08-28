export type FuelCode = "gazole" | "sp95" | "sp98" | "e10" | "e85" | "gplc";

export interface FuelInfo {
  code: FuelCode;
  label: string;
}

export interface LatLon {
  lat: number;
  lon: number;
}

export interface StationSearchItem {
  id: number;
  address: string | null;
  city: string | null;
  postal_code: string | null;
  road_type: string | null;
  lat: number;
  lon: number;
  distance_m: number;
  price_eur: number | null;
  price_updated_at: string | null;
  outage: "none" | "temporary" | "definitive";
  cheapest_delta_eur: number | null;
}

export interface StationSearchResponse {
  items: StationSearchItem[];
  total: number;
  page: number;
  page_size: number;
  data_updated_at: string | null;
  stale: boolean;
}

export interface BeMaxPrice {
  fuel_code: string;
  product_label: string;
  price_eur: number;
  price_date: string;
}

export interface BeMaxPriceResponse {
  prices: BeMaxPrice[];
  fetched_at: string | null;
}
