"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface PaginationProps {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  className?: string;
}

/**
 * Simple page-number pagination with prev/next controls.
 * `page` is 1-based; `pageCount` is the total number of pages.
 */
export function Pagination({
  page,
  pageCount,
  onPageChange,
  className,
}: PaginationProps) {
  const canPrev = page > 1;
  const canNext = page < pageCount;

  const go = (next: number) => {
    const clamped = Math.min(Math.max(next, 1), Math.max(pageCount, 1));
    if (clamped !== page) onPageChange(clamped);
  };

  if (pageCount <= 1) return null;

  return (
    <nav
      className={cn("flex items-center justify-between gap-2", className)}
      aria-label="Pagination"
    >
      <Button
        variant="outline"
        size="sm"
        onClick={() => go(page - 1)}
        disabled={!canPrev}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
        Prev
      </Button>
      <span className="text-sm text-muted-foreground" aria-live="polite">
        Page {page} of {pageCount}
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={() => go(page + 1)}
        disabled={!canNext}
        aria-label="Next page"
      >
        Next
        <ChevronRight className="h-4 w-4" />
      </Button>
    </nav>
  );
}

export default Pagination;
