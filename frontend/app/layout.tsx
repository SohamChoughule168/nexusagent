import type { Metadata } from "next";
import { AppProviders } from "@/app/providers";
import { env } from "@/lib/env";
import "./globals.css";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://nexusagent.dev";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${env.appName} — The AI agent platform that knows your business`,
    template: `%s · ${env.appName}`,
  },
  description:
    "NexusAgent is a multi-tenant AI agent platform. Build, ground, and orchestrate autonomous agents on your own knowledge with memory, tools, and multi-agent routing.",
  keywords: [
    "AI agents",
    "RAG",
    "chatbot platform",
    "conversational AI",
    "knowledge base",
    "agent orchestration",
  ],
  applicationName: env.appName,
  alternates: {
    canonical: SITE_URL,
  },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: env.appName,
    title: `${env.appName} — The AI agent platform that knows your business`,
    description:
      "Build, ground, and orchestrate autonomous AI agents on your own knowledge.",
  },
  twitter: {
    card: "summary_large_image",
    title: `${env.appName} — The AI agent platform that knows your business`,
    description:
      "Build, ground, and orchestrate autonomous AI agents on your own knowledge.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: env.appName,
      url: SITE_URL,
      description:
        "NexusAgent is a multi-tenant AI agent platform for building, grounding, and orchestrating autonomous agents on your own knowledge.",
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: env.appName,
      publisher: { "@id": `${SITE_URL}/#organization` },
      potentialAction: {
        "@type": "SearchAction",
        target: `${SITE_URL}/#docs`,
        "query-input": "required name=search",
      },
    },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        <a
          href="#main-content"
          className="sr-only left-4 top-4 z-[200] rounded-md bg-background px-4 py-2 text-sm font-medium shadow focus:not-sr-only focus:fixed focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Skip to content
        </a>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
