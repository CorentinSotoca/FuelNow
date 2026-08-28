import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchBePrices, searchStations } from "../api";
import type { BeMaxPriceResponse, FuelCode, LatLon, StationSearchResponse } from "../types";
import { isInBelgium } from "../utils";

export type SearchErrorKind = "rate_limit" | "network" | "server" | "invalid";

export interface SearchError {
  kind: SearchErrorKind;
  message: string;
}

interface UseDebouncedSearchParams {
  point: LatLon | null;
  radiusM: number;
  fuel: FuelCode;
  sort: "price" | "distance";
  debounceMs?: number;
}

function classifyError(e: unknown): SearchError {
  if (e instanceof ApiError) {
    if (e.status === 429) return { kind: "rate_limit", message: e.message };
    if (e.status === 422) return { kind: "invalid", message: e.message };
    return { kind: "server", message: e.message };
  }
  return { kind: "network", message: "Erreur réseau. Vérifiez votre connexion." };
}

export function useDebouncedSearch({
  point,
  radiusM,
  fuel,
  sort,
  debounceMs = 400,
}: UseDebouncedSearchParams) {
  const [data, setData] = useState<StationSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<SearchError | null>(null);
  const [bePrices, setBePrices] = useState<BeMaxPriceResponse | null>(null);
  const [beLoading, setBeLoading] = useState(false);
  const reqIdRef = useRef(0);

  const inBelgium = point ? isInBelgium(point.lat, point.lon) : false;

  const execute = useCallback(
    async (p: LatLon, r: number, f: FuelCode, s: "price" | "distance") => {
      const reqId = ++reqIdRef.current;
      setLoading(true);
      setError(null);
      try {
        const res = await searchStations({ point: p, radiusM: r, fuel: f, sort: s });
        if (reqId !== reqIdRef.current) return;
        setData(res);
      } catch (e) {
        if (reqId !== reqIdRef.current) return;
        setError(classifyError(e));
      } finally {
        if (reqId === reqIdRef.current) setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!point) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    const timer = setTimeout(() => execute(point, radiusM, fuel, sort), debounceMs);
    return () => clearTimeout(timer);
  }, [point?.lat, point?.lon, radiusM, fuel, sort, debounceMs, point, execute]);

  useEffect(() => {
    if (!inBelgium) {
      setBePrices(null);
      setBeLoading(false);
      return;
    }
    setBeLoading(true);
    fetchBePrices()
      .then(setBePrices)
      .catch(() => setBePrices(null))
      .finally(() => setBeLoading(false));
  }, [inBelgium]);

  const retry = useCallback(() => {
    if (point) execute(point, radiusM, fuel, sort);
  }, [point, radiusM, fuel, sort, execute]);

  return { data, loading, error, retry, inBelgium, bePrices, beLoading };
}
