"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, LayoutDashboard, MessageSquare, BookOpen, Boxes } from "lucide-react";
import { cn } from "@/lib/utils";
import { env } from "@/lib/env";

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Not-yet-built areas are listed but not active. */
  disabled?: boolean;
}

/**
 * Primary navigation. Knowledge Base / Chat / Agent Builder are active.
 */
const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/knowledge-bases", label: "Knowledge Base", icon: BookOpen },
  { href: "/agents", label: "Agent Builder", icon: Boxes },
];

export interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "flex w-64 flex-col border-r bg-card transition-transform",
        className,
      )}
      aria-label="Primary"
    >
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Bot className="h-4 w-4" />
        </div>
        <span className="text-lg font-semibold">{env.appName}</span>
      </div>

      <nav className="flex-1 space-y-1 p-4">
        {NAV_ITEMS.map((item) => {
          const active =
            !item.disabled &&
            (pathname === item.href || pathname.startsWith(`${item.href}/`));
          const Icon = item.icon;
          const content = (
            <span
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                item.disabled && "cursor-not-allowed opacity-50",
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
              {item.disabled && (
                <span className="ml-auto text-xs text-muted-foreground">
                  Soon
                </span>
              )}
            </span>
          );

          if (item.disabled) {
            return (
              <div key={item.href} aria-disabled="true">
                {content}
              </div>
            );
          }

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
            >
              {content}
            </Link>
          );
        })}
      </nav>

      <div className="border-t p-4 text-xs text-muted-foreground">
        {env.appName} · Milestone 6 Phase 4
      </div>
    </aside>
  );
}

export default Sidebar;
