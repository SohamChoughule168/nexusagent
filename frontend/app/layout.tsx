import type { Metadata } from "next";
import { AppProviders } from "@/app/providers";
import { env } from "@/lib/env";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: `${env.appName} — AI Agent Platform`,
    template: `%s · ${env.appName}`,
  },
  description:
    "NexusAgent AI — build, orchestrate, and chat with autonomous agents.",
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
