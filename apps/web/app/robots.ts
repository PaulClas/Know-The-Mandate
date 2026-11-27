import type { MetadataRoute } from "next";

import { SITE } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: ["/", "/about", "/llms.txt"], disallow: ["/api/", "/bank/", "/oauth/", "/adapters/"] }],
    sitemap: `${SITE}/sitemap.xml`,
  };
}
