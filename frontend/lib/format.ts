export const usd = (n: number | null | undefined) =>
  n == null ? "—" : "$" + Math.round(n).toLocaleString("en-US");
export const usdK = (n: number | null | undefined) =>
  n == null ? "—" : "$" + Math.round(n / 1000).toLocaleString("en-US") + "K";
export const pct = (n: number | null | undefined, d = 1) => (n == null ? "—" : (n * 100).toFixed(d) + "%");
export const signedPct = (n: number | null | undefined, d = 1) =>
  n == null ? "—" : (n > 0 ? "+" : "") + (n * 100).toFixed(d) + "%";
export const monthYear = (iso: string) =>
  new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "short", year: "2-digit" });
