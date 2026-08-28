import { memo } from "react";
import type { StationSearchItem } from "../types";
import type { Quartiles } from "../utils";
import { formatDelta, formatDistance, formatHoursAgo, formatPrice, quartileColor } from "../utils";

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
  const labelParts = [station.address, [station.postal_code, station.city].filter(Boolean).join(" ")].filter(Boolean);
  const label = encodeURIComponent(labelParts.join(", "));
  const itineraryUrl = `geo:${station.lat},${station.lon}?q=${station.lat},${station.lon}${label ? `(${label})` : ""}`;

  return (
    <div
      className={`station-card${selected ? " selected" : ""}`}
      onClick={() => onSelect(station.id)}
      onMouseEnter={() => onHover(station.id)}
      onMouseLeave={() => onHover(null)}
      role="button"
      tabIndex={0}
      aria-label={`Station ${station.address ?? ""} ${station.postal_code ?? ""} ${station.city ?? ""}, ${formatPrice(station.price_eur)}, ${formatDistance(station.distance_m)}`}
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
          <a
            href={itineraryUrl}
            className="itinerary-link"
            onClick={(e) => e.stopPropagation()}
          >
            Itinéraire →
          </a>
        </div>
      </div>
    </div>
  );
}

export const StationCard = memo(StationCardInner);
