import * as React from "react";
import { cn } from "@/lib/utils";

/** Marketing feature card with an icon tile, title, and description. */
export function FeatureCard({
  icon,
  title,
  description,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border border-border bg-card p-6 transition-colors hover:border-brand-300",
        className,
      )}
    >
      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg bg-brand-500/10 text-brand-600 transition-colors group-hover:bg-brand-500 group-hover:text-white">
        {icon}
      </div>
      <h3 className="mb-1.5 text-base font-semibold text-foreground">
        {title}
      </h3>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {description}
      </p>
    </div>
  );
}

export default FeatureCard;
