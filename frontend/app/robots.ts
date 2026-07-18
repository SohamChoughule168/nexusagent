import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://nexusagent.dev";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/api/", "/dashboard", "/chat", "/agents", "/knowledge-bases"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
