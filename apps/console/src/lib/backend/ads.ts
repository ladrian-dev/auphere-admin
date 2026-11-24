import type { Call } from "../backend";

/**
 * Carril del informe de anuncios de un cliente (spec 076, requisito 3):
 * `contracts/api-y-eventos.md` §2.3. Se esparce en `backendFor`.
 *
 * Sin nombres ni teléfonos de clientes finales: el titular es texto del
 * anunciante. `days` solo admite 7, 30 o 90 (la API responde 422 a otro).
 */

export const ADS_PERIODS = [7, 30, 90] as const;
export type AdsPeriod = (typeof ADS_PERIODS)[number];

export type AdsReportRow = {
  /** `null`: clics sin identificador de anuncio, juntos en una fila. */
  ad_id: string | null;
  ad_kind: "ad" | "post";
  ad_headline: string | null;
  ad_url: string | null;
  /** Conversaciones con un clic de este anuncio en el periodo. */
  conversations: number;
  /** Reservas del agente del periodo atribuidas a este anuncio, no canceladas. */
  bookings: number;
  amounts: { currency: string; amount_minor: number }[];
};

export type AdsReport = { days: number; rows: AdsReportRow[] };

export function adsApi(call: Call) {
  const enc = encodeURIComponent;
  return {
    adsReport: (ref: string, days: AdsPeriod) => call<AdsReport>(`/console/clients/${enc(ref)}/ads/report?days=${days}`),
  };
}
