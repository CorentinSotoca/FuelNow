import { memo } from "react";
import type { StationSearchItem } from "../types";
import type { Quartiles } from "../utils";
import {
  formatDelta,
  formatDistance,
  formatHoursAgo,
  formatPrice,
  quartileColor,
  stationNavLinks,
  stationTitle,
} from "../utils";

interface StationCardProps {
  station: StationSearchItem;
  rank: number;
  quartiles: Quartiles | null;
  selected: boolean;
  onSelect: (id: number) => void;
  onHover: (id: number | null) => void;
}

function StationCardInner({
  station,
  rank,
  quartiles,
  selected,
  onSelect,
  onHover,
}: StationCardProps) {
  const color = quartileColor(station.price_eur, quartiles);
  const isCheapest = station.cheapest_delta_eur === null || station.cheapest_delta_eur === 0;
  const isAutoroute = station.road_type === "A";
  const title = stationTitle(station);
  const nav = stationNavLinks(station);

  return (
    <div
      className={`station-card${selected ? " selected" : ""}`}
      onClick={() => onSelect(station.id)}
      onMouseEnter={() => onHover(station.id)}
      onMouseLeave={() => onHover(null)}
      role="button"
      tabIndex={0}
      aria-label={`Station ${title ? `${title}, ` : ""}${station.address ?? ""} ${station.postal_code ?? ""} ${station.city ?? ""}, ${formatPrice(station.price_eur)}, ${formatDistance(station.distance_m)}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(station.id);
        }
      }}
    >
      <div className="station-card-rank" style={{ background: color }}>
        {rank}
      </div>

      <div className="station-card-body">
        <div className="station-card-top">
          <span className="station-card-price" style={{ color }}>
            {formatPrice(station.price_eur)}
          </span>
          <span className="station-card-distance">{formatDistance(station.distance_m)}</span>
        </div>

        <div className="station-card-delta">
          {isCheapest ? (
            <span className="badge-cheapest">Moins cher</span>
          ) : (
            <span className="badge-delta">{formatDelta(station.cheapest_delta_eur)}</span>
          )}
        </div>

        {title ? <div className="station-card-title">{title}</div> : null}

        <div className="station-card-address">
          {station.address ?? "Adresse non renseignée"}
          {station.postal_code || station.city ? (
            <>
              <br />
              {[station.postal_code, station.city].filter(Boolean).join(" ")}
            </>
          ) : null}
        </div>

        <div className="station-card-footer">
          {isAutoroute && <span className="badge-road">Autoroute</span>}
          {station.price_updated_at && (
            <span className="station-card-maj">MAJ {formatHoursAgo(station.price_updated_at)}</span>
          )}
          <div className="station-card-nav">
            <a
              href={nav.waze}
              className="nav-btn nav-btn-waze"
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              aria-label={`Ouvrir l'enseigne ${title || "de la station"} dans Waze`}
            >
              Waze
            </a>
            <a
              href={nav.maps}
              className="nav-btn nav-btn-maps"
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              aria-label={`Ouvrir l'enseigne ${title || "de la station"} dans Google Maps`}
            >
              Maps
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

export const StationCard = memo(StationCardInner);
