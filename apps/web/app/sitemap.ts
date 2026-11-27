import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const pages = ["", "/about", "/proof", "/standards", "/ontology", "/scenarios"];
  return pages.map((p) => ({ url: `${SITE}${p}`, lastModified: new Date("2026-11-26"), changeFrequency: "monthly", priority: p === "" || p === "/about" ? 1 : 0.6 }));
}
