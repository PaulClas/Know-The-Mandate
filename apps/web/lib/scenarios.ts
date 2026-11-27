import type { ScenarioMeta } from "./types";

export function isScenarioC(s: Pick<ScenarioMeta, "id" | "title">): boolean {
  const id = s.id.toLowerCase();
  return /(^|[_\-.])c($|[_\-.])/.test(id) || /^c\d*$/.test(id) || /^scenario\s*c\b/i.test(s.title) || /^c[\s.:\-–—]/i.test(s.title);
}

/** Letter label (A..M) derived from id or title when possible. */
export function scenarioLetter(s: Pick<ScenarioMeta, "id" | "title">): string | null {
  const t = s.title.match(/^(?:scenario\s*)?([A-M])\b/i);
  if (t) return t[1].toUpperCase();
  const i = s.id.match(/(?:^|[_\-.])([a-m])(?:$|[_\-.])/i);
  return i ? i[1].toUpperCase() : null;
}
