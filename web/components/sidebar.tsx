"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { MessageSquare, BookOpen, Settings as SettingsIcon, FolderOpen, Trash2, Plus, Plug, Loader2, Search, GitCompare } from "lucide-react";
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
import { useActiveStreamIds } from "@/lib/streams";
import { useT } from "@/lib/i18n/context";

const SIDEBAR_WIDTH = 240;

// Nav items keyed for i18n; `labelKey` resolves via the t() function
// at render time so the sidebar updates instantly when language flips.
const NAV: Array<{ href: string; labelKey: string; icon: typeof MessageSquare }> = [
  { href: "/",            labelKey: "sidebar.nav.faroai",      icon: MessageSquare },
  { href: "/evaluate",    labelKey: "sidebar.nav.evaluate",    icon: Search },
  { href: "/compare",     labelKey: "sidebar.nav.compare",     icon: GitCompare },
  { href: "/skills",      labelKey: "sidebar.nav.skills",      icon: BookOpen },
  { href: "/settings",    labelKey: "sidebar.nav.settings",    icon: SettingsIcon },
  { href: "/files",       labelKey: "sidebar.nav.files",       icon: FolderOpen },
  { href: "/connections", labelKey: "sidebar.nav.connections", icon: Plug },
];

export function Sidebar() {
  const t = useT();
  const pathname = usePathname();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  // Set of conversation ids that have an in-flight stream — drives the
  // little spinner next to streaming conversations in the recent list.
  const activeStreamIds = useActiveStreamIds();

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
    if (!confirm(t("sidebar.delete_confirm"))) return;
    deleteConversation(id);
  }

  const groups = groupByRecency(conversations);

  return (
    <aside className="sidebar" style={{ width: SIDEBAR_WIDTH }}>
      <div className="sidebar-wordmark">FaroLatino</div>
      <nav className="sidebar-nav">
        {NAV.map(({ href, labelKey, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn("sidebar-link", active && "sidebar-link-active")}
            >
              <Icon size={16} strokeWidth={1.75} />
              <span>{t(labelKey)}</span>
            </Link>
          );
        })}
        <button
          type="button"
          className="sidebar-link sidebar-link-action"
          onClick={startNewChat}
          title={t("sidebar.new_chat")}
        >
          <Plus size={16} strokeWidth={1.75} />
          <span>{t("sidebar.new_chat")}</span>
        </button>
      </nav>

      {conversations.length > 0 && (
        <div className="sidebar-history">
          {groups.map((g) => (
            <div key={g.labelKey} className="sidebar-history-group">
              <div className="sidebar-history-label">{t(g.labelKey)}</div>
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
                  {activeStreamIds.has(c.id) && (
                    <Loader2 size={12} className="spin" aria-label="thinking" />
                  )}
                  <span className="sidebar-history-title">{c.title}</span>
                  <button
                    type="button"
                    className="sidebar-history-del"
                    onClick={(e) => remove(e, c.id)}
                    title={t("sidebar.delete_title")}
                    aria-label={t("sidebar.delete_title")}
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
