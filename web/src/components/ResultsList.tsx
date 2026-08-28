import { useEffect, useRef } from "react";
import type { LatLon, StationSearchItem } from "../types";
import type { Quartiles } from "../utils";
import { priceQuartiles } from "../utils";
import type { SearchError } from "../hooks/useDebouncedSearch";
import { StationCard } from "./StationCard";

interface ResultsListProps {
  data: { items: StationSearchItem[]; total: number; stale: boolean; data_updated_at: string | null } | null;
  loading: boolean;
  error: SearchError | null;
  searchPoint: LatLon;
  selectedStationId: number | null;
  radiusM: number;
  sort: "price" | "distance";
  onSortChange: (sort: "price" | "distance") => void;
  onSelectStation: (id: number) => void;
  onHoverStation: (id: number | null) => void;
  onRetry: () => void;
  onExpandRadius: (deltaM: number) => void;
}

export function ResultsList({
  data,
  loading,
  error,
  searchPoint,
  selectedStationId,
  radiusM,
  sort,
  onSortChange,
  onSelectStation,
  onHoverStation,
  onRetry,
  onExpandRadius,
}: ResultsListProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const items = data?.items ?? [];
  const quartiles: Quartiles | null = priceQuartiles(items);

  useEffect(() => {
    if (selectedStationId === null) return;
    const el = cardRefs.current.get(selectedStationId);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedStationId]);

  if (loading) {
    return (
      <div className="results-state">
        <div className="spinner" />
        <p>Recherche en cours…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="results-state error">
        {error.kind === "rate_limit" && (
          <>
            <p>⏳ {error.message}</p>
            <button className="btn-retry" onClick={onRetry}>
              Réessayer
            </button>
          </>
        )}
        {error.kind === "network" && (
          <>
            <p>📡 {error.message}</p>
            <button className="btn-retry" onClick={onRetry}>
              Réessayer
            </button>
          </>
        )}
        {error.kind === "server" && (
          <>
            <p>⚠️ {error.message}</p>
            <button className="btn-retry" onClick={onRetry}>
              Réessayer
            </button>
          </>
        )}
        {error.kind === "invalid" && <p>⚠️ {error.message}</p>}
      </div>
    );
  }

  if (!data || items.length === 0) {
    return (
      <div className="results-state empty">
        <p>Aucune station trouvée dans ce rayon.</p>
        <button className="btn-expand" onClick={() => onExpandRadius(5000)}>
          Élargir le rayon de 5 km
        </button>
      </div>
    );
  }

  return (
    <div className="results-container">
      {data.stale && (
        <div className="stale-banner">
          ⚠️ Données potentiellement obsolètes (dernière mise à jour ETL il y a plus de 26 h).
        </div>
      )}

      <div className="results-header">
        <span className="results-count">
          {data.total} station{data.total > 1 ? "s" : ""} — rayon {(radiusM / 1000).toFixed(1)} km
        </span>
        <div className="sort-toggle">
          <button
            type="button"
            className={sort === "price" ? "sort-btn selected" : "sort-btn"}
            onClick={() => onSortChange("price")}
          >
            Prix
          </button>
          <button
            type="button"
            className={sort === "distance" ? "sort-btn selected" : "sort-btn"}
            onClick={() => onSortChange("distance")}
          >
            Distance
          </button>
        </div>
      </div>

      <div className="results-list" ref={listRef}>
        {items.map((station, i) => (
          <div
            key={station.id}
            ref={(el) => {
              if (el) cardRefs.current.set(station.id, el);
              else cardRefs.current.delete(station.id);
            }}
          >
            <StationCard
              station={station}
              rank={i + 1}
              quartiles={quartiles}
              selected={station.id === selectedStationId}
              searchPoint={searchPoint}
              onSelect={onSelectStation}
              onHover={onHoverStation}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
