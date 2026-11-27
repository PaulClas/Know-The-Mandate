// Money helpers. Amounts are integer minor units; no floating point arithmetic is ever performed on them.

const ZERO_DECIMAL = new Set(["JPY", "KRW", "VND", "CLP", "ISK", "UGX", "XAF", "XOF"]);
const THREE_DECIMAL = new Set(["BHD", "JOD", "KWD", "OMR", "TND"]);

export function minorDigits(currency: string | null | undefined): number {
  const c = (currency ?? "CAD").toUpperCase();
  if (ZERO_DECIMAL.has(c)) return 0;
  if (THREE_DECIMAL.has(c)) return 3;
  return 2;
}

/** 8500, "CAD" -> "CAD 85.00" (grouping via Intl on the integer part; fraction handled as integer digits). */
export function formatMoney(minor: number | null | undefined, currency?: string | null, locale = "en-CA"): string {
  if (minor === null || minor === undefined || !Number.isFinite(minor)) return "—";
  const d = minorDigits(currency);
  const neg = minor < 0;
  const abs = BigInt(Math.abs(Math.trunc(minor)));
  const base = 10n ** BigInt(d);
  const whole = new Intl.NumberFormat(locale).format(abs / base);
  const frac = d === 0 ? "" : "." + (abs % base).toString().padStart(d, "0");
  return `${neg ? "-" : ""}${currency ?? ""} ${whole}${frac}`.trim();
}

/** "85.5" -> 8550 (string parsing, no floats). Returns null for invalid input. */
export function parseMajorToMinor(input: string, currency?: string | null): number | null {
  const d = minorDigits(currency);
  const m = input.trim().match(/^(\d+)(?:\.(\d+))?$/);
  if (!m) return null;
  const frac = (m[2] ?? "");
  if (frac.length > d) return null;
  const minor = BigInt(m[1]) * 10n ** BigInt(d) + BigInt(frac.padEnd(d, "0") || "0");
  if (minor > BigInt(Number.MAX_SAFE_INTEGER)) return null;
  return Number(minor);
}

/** 8550 -> "85.50" (plain, for inputs). */
export function minorToMajorString(minor: number | null | undefined, currency?: string | null): string {
  if (minor === null || minor === undefined) return "";
  const d = minorDigits(currency);
  const abs = BigInt(Math.abs(Math.trunc(minor)));
  const base = 10n ** BigInt(d);
  const frac = d === 0 ? "" : "." + (abs % base).toString().padStart(d, "0");
  return `${minor < 0 ? "-" : ""}${(abs / base).toString()}${frac}`;
}
