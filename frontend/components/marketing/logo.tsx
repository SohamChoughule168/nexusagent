import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { env } from "@/lib/env";

/**
 * Inline NexusAgent logo: the nexus mark (three connected nodes in the brand
 * gradient) plus the wordmark. Rendered inline so it stays crisp and can adopt
 * the brand gradient / currentColor.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      role="img"
      aria-label="NexusAgent"
      className={cn("h-7 w-7", className)}
    >
      <defs>
        <linearGradient
          id="nxLogoGrad"
          x1="2"
          y1="2"
          x2="30"
          y2="30"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#7C5CFF" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <path
        d="M16 6.5 L7.5 23.5 L24.5 23.5 Z"
        stroke="url(#nxLogoGrad)"
        strokeWidth="2.2"
        strokeLinejoin="round"
        opacity="0.55"
      />
      <circle cx="16" cy="6.5" r="3.4" fill="url(#nxLogoGrad)" />
      <circle cx="7.5" cy="23.5" r="3.4" fill="url(#nxLogoGrad)" />
      <circle cx="24.5" cy="23.5" r="3.4" fill="url(#nxLogoGrad)" />
    </svg>
  );
}

export function Logo({
  className,
  showWordmark = true,
  href = "/",
}: {
  className?: string;
  showWordmark?: boolean;
  href?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex items-center gap-2 font-semibold tracking-tight text-foreground",
        className,
      )}
    >
      <LogoMark />
      {showWordmark && (
        <span className="text-lg">
          {env.appName}
        </span>
      )}
    </Link>
  );
}

export default Logo;
