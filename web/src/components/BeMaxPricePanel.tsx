import type { BeMaxPriceResponse } from "../types";
import type { FuelCode } from "../types";
import { formatBeDate, formatPrice } from "../utils";

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

  const selectedPrice = bePrices.prices.find((p) => p.fuel_code === fuel);
  const priceDate = bePrices.prices[0]?.price_date;
  const label = selectedPrice
    ? BE_FUEL_LABELS[selectedPrice.fuel_code] ?? selectedPrice.product_label
    : BE_FUEL_LABELS[fuel] ?? fuel;

  return (
    <div className="be-max-price-panel">
      <div className="be-panel-header">🇧🇪 Prix max Belgique</div>
      {selectedPrice ? (
        <div className="be-panel-body">
          <div className="be-panel-fuel">{label}</div>
          <div className="be-panel-price">{formatPrice(selectedPrice.price_eur)}</div>
          <div className="be-panel-date">
            Prix max au {formatBeDate(priceDate)}
          </div>
        </div>
      ) : (
        <p className="be-panel-unavailable">
          {label} non disponible en Belgique.
        </p>
      )}
    </div>
  );
}
