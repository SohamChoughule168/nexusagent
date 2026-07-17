import React, { forwardRef } from "react";
import { cn } from "@/lib/utils";

interface SearchBarProps extends React.InputHTMLAttributes<HTMLInputElement> {
  /** Optional label for accessibility */
  label?: string;
}

const SearchBar = forwardRef<HTMLInputElement, SearchBarProps>(
  ({ className, label, placeholder = "Search...", ...props }, ref) => {
    return (
      <div className="relative">
        <label htmlFor={props.id} className="sr-only">
          {label ?? "Search"}
        </label>
        <input
          type="search"
          ref={ref}
          className={cn(
            "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 pl-10",
            className,
          )}
          placeholder={placeholder}
          {...props}
        />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </span>
      </div>
    );
  },
);

SearchBar.displayName = "SearchBar";

export { SearchBar };