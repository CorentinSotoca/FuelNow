import type { BeMaxPriceResponse } from "../types";
import type { FuelCode } from "../types";
import { bePriceForFuel, formatBeDate, formatPrice } from "../utils";

interface BeMaxPricePanelProps {
  bePrices: BeMaxPriceResponse | null;
  loading: boolean;
  fuel: FuelCode;
}

const BE_FUEL_LABELS: Record<string, string> = {
  gazole: "Diesel B7",
  sp95: "Essence 95 E5",
  sp98: "Essence 98 E5",
  e10: "Essence 95 E10",
  gplc: "Autogas LPG",
  e85: "E85",
};

export function BeMaxPricePanel({ bePrices, loading, fuel }: BeMaxPricePanelProps) {
  if (loading) {
    return (
      <div className="be-max-price-panel">
        <div className="be-panel-header">🇧🇪 Prix max Belgique</div>
        <p className="be-panel-loading">Chargement…</p>
      </div>
    );
  }

  if (!bePrices || bePrices.prices.length === 0) {
    return (
      <div className="be-max-price-panel">
        <div className="be-panel-header">🇧🇪 Prix max Belgique</div>
        <p className="be-panel-unavailable">Prix maximum non disponible pour ce carburant.</p>
      </div>
    );
  }

  const selectedPrice = bePriceForFuel(bePrices, fuel);
  const priceDate = selectedPrice?.price_date;
  const label = fuel === "sp95-e10"
    ? "Essence 95 (E5/E10)"
    : selectedPrice
      ? BE_FUEL_LABELS[selectedPrice.fuel_code] ?? selectedPrice.product_label
      : BE_FUEL_LABELS[fuel] ?? fuel;

  return (
    <div className="be-max-price-panel">
      <div className="be-panel-row">
        <span className="be-panel-header">🇧🇪 Prix max Belgique</span>
        {selectedPrice ? (
          <span className="be-panel-price">{formatPrice(selectedPrice.price_eur)}</span>
        ) : (
          <span className="be-panel-unavailable">{label} : N/A</span>
        )}
      </div>
      {selectedPrice ? (
        <div className="be-panel-row be-panel-sub">
          <span className="be-panel-fuel">{label}</span>
          <span className="be-panel-date">au {formatBeDate(priceDate ?? "")}</span>
        </div>
      ) : null}
    </div>
  );
}
