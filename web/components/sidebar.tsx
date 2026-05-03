"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { MessageSquare, BookOpen, Brain, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";

// 240px wide is wide enough for "FAROLATINO" + 4 nav items at 14px font.
// Anything narrower and the wordmark wraps; anything wider eats into the
// chat column.
const SIDEBAR_WIDTH = 240;

const NAV = [
  { href: "/",        label: "FaroAI",  icon: MessageSquare },
  { href: "/skills",  label: "Skills",  icon: BookOpen },
  { href: "/memory",  label: "Memory",  icon: Brain },
  { href: "/files",   label: "Files",   icon: FolderOpen },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside
      className="sidebar"
      style={{ width: SIDEBAR_WIDTH }}
    >
      <div className="sidebar-wordmark">FaroLatino</div>
      <nav className="sidebar-nav">
        {NAV.map(({ href, label, icon: Icon }) => {
          // Use exact match for `/` so `/skills` doesn't ALSO mark FaroAI active.
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn("sidebar-link", active && "sidebar-link-active")}
            >
              <Icon size={16} strokeWidth={1.75} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

export const SIDEBAR_WIDTH_PX = SIDEBAR_WIDTH;
