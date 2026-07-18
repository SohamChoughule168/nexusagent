import type { Metadata } from "next";
import { AppProviders } from "@/app/providers";
import { env } from "@/lib/env";
import "./globals.css";

export const metadata: Metadata = {
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
  openGraph: {
    title: `${env.appName} — The AI agent platform that knows your business`,
    description:
      "Build, ground, and orchestrate autonomous AI agents on your own knowledge.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
