"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { MessageSquare, BookOpen, Brain, FolderOpen, Trash2, Plus, Plug } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  type Conversation,
  deleteConversation,
  getActiveConversationId,
  groupByRecency,
  listConversations,
  setActiveConversationId,
  subscribeToConversations,
} from "@/lib/conversations";

const SIDEBAR_WIDTH = 240;

const NAV = [
  { href: "/",            label: "FaroAI",      icon: MessageSquare },
  { href: "/skills",      label: "Skills",      icon: BookOpen },
  { href: "/memory",      label: "Memory",      icon: Brain },
  { href: "/files",       label: "Files",       icon: FolderOpen },
  { href: "/connections", label: "Connections", icon: Plug },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  // Read the conversation list + active id on mount + on every change
  // event (driven by chat.tsx's saveConversation calls + cross-tab via
  // the storage event).
  useEffect(() => {
    const sync = () => {
      setConversations(listConversations());
      setActiveId(getActiveConversationId());
    };
    sync();
    return subscribeToConversations(sync);
  }, []);

  function pick(id: string) {
    setActiveConversationId(id);
    // Always send the user back to the chat route — clicking a past
    // conversation from /skills or /files should land on /.
    if (pathname !== "/") router.push("/");
  }

  function startNewChat() {
    setActiveConversationId(null);
    if (pathname !== "/") router.push("/");
  }

  function remove(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!confirm("Delete this conversation? This can't be undone.")) return;
    deleteConversation(id);
  }

  const groups = groupByRecency(conversations);

  return (
    <aside className="sidebar" style={{ width: SIDEBAR_WIDTH }}>
      <div className="sidebar-wordmark">FaroLatino</div>
      <nav className="sidebar-nav">
        {NAV.map(({ href, label, icon: Icon }) => {
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
        <button
          type="button"
          className="sidebar-link sidebar-link-action"
          onClick={startNewChat}
          title="Clear the chat and start a new conversation"
        >
          <Plus size={16} strokeWidth={1.75} />
          <span>New chat</span>
        </button>
      </nav>

      {conversations.length > 0 && (
        <div className="sidebar-history">
          {groups.map((g) => (
            <div key={g.label} className="sidebar-history-group">
              <div className="sidebar-history-label">{g.label}</div>
              {g.items.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={cn(
                    "sidebar-history-item",
                    pathname === "/" && c.id === activeId && "sidebar-history-item-active",
                  )}
                  onClick={() => pick(c.id)}
                  title={c.title}
                >
                  <span className="sidebar-history-title">{c.title}</span>
                  <button
                    type="button"
                    className="sidebar-history-del"
                    onClick={(e) => remove(e, c.id)}
                    title="Delete conversation"
                    aria-label="Delete conversation"
                  >
                    <Trash2 size={12} />
                  </button>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}

export const SIDEBAR_WIDTH_PX = SIDEBAR_WIDTH;
