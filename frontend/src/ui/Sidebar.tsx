// The app sidebar: brand, tools, and conversation history.
//
// Layout, top to bottom:
//   header   collapse + search on the left, NTT DATA mark on the right
//   action   New chat
//   Tools    Assistant / Report Generator
//   Pinned   pinned conversations, kept above the rest
//   Chats    everything else, newest first
//   footer   system status + user menu
//
// Conversations live here rather than in a second rail, because two sidebars
// consumed ~480px before any content. Each row supports rename (inline),
// pin/unpin, and delete.

import React, { useEffect, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  FileText,
  MessageSquare,
  MoreHorizontal,
  PanelLeft,
  PanelLeftClose,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import type { Conversation } from '../api/chat';
import { NttLogo, NttMark, NTT_BLUE } from './Brand';

export type Tool = 'chatbot' | 'reports';

interface Props {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onOpenSearch: () => void;

  tool: Tool;
  onSelectTool: (tool: Tool) => void;

  conversations: Conversation[];
  activeId: string | null;
  onSelectConversation: (id: string | null) => void;
  onRename: (id: string, title: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onDelete: (id: string) => void;
  pinningSupported: boolean;

  footer: React.ReactNode;
}

const TOOLS: { id: Tool; label: string; icon: React.ReactNode }[] = [
  { id: 'chatbot', label: 'Assistant', icon: <MessageSquare className="w-[18px] h-[18px]" /> },
  { id: 'reports', label: 'Report Generator', icon: <FileText className="w-[18px] h-[18px]" /> },
];

export default function Sidebar({
  collapsed,
  onToggleCollapsed,
  onOpenSearch,
  tool,
  onSelectTool,
  conversations,
  activeId,
  onSelectConversation,
  onRename,
  onTogglePin,
  onDelete,
  pinningSupported,
  footer,
}: Props) {
  const pinned = conversations.filter((c) => c.pinned);
  const rest = conversations.filter((c) => !c.pinned);

  return (
    <aside
      className={`flex shrink-0 flex-col border-r border-slate-200 bg-slate-50/70 transition-[width] duration-200 dark:border-slate-800 dark:bg-[#0d1524] ${
        collapsed ? 'w-[64px]' : 'w-[264px]'
      }`}
    >
      {/* ── Header ─────────────────────────────────────────────────────────
          Controls on the left, brand on the right — so the brand keeps the
          same optical position whether the sidebar is open or closed. */}
      <div className="flex h-14 items-center gap-1 px-2.5">
        <button
          onClick={onToggleCollapsed}
          title={`${collapsed ? 'Expand' : 'Collapse'} sidebar  ⌘\\`}
          className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
        >
          {collapsed ? <PanelLeft className="w-[18px] h-[18px]" /> : <PanelLeftClose className="w-[18px] h-[18px]" />}
        </button>

        {!collapsed && (
          <>
            <button
              onClick={onOpenSearch}
              title="Search conversations  ⌘K"
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
            >
              <Search className="w-[18px] h-[18px]" />
            </button>
            <div className="ml-auto pr-0.5">
              <NttLogo height={19} />
            </div>
          </>
        )}
      </div>

      {collapsed ? (
        <div className="flex flex-col items-center gap-1 px-2">
          <button
            onClick={onOpenSearch}
            title="Search  ⌘K"
            className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800"
          >
            <Search className="w-[18px] h-[18px]" />
          </button>
          <button
            onClick={() => { onSelectTool('chatbot'); onSelectConversation(null); }}
            title="New chat"
            className="rounded-lg p-2 text-white transition hover:brightness-110"
            style={{ background: NTT_BLUE }}
          >
            <Plus className="w-[18px] h-[18px]" />
          </button>
          {TOOLS.map((t) => (
            <button
              key={t.id}
              onClick={() => onSelectTool(t.id)}
              title={t.label}
              className={`rounded-lg p-2 transition ${
                tool === t.id
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-slate-100'
                  : 'text-slate-400 hover:bg-slate-200/60 dark:hover:bg-slate-800'
              }`}
              style={tool === t.id ? { color: NTT_BLUE } : undefined}
            >
              {t.icon}
            </button>
          ))}
        </div>
      ) : (
        <>
          <div className="px-2.5 pb-2">
            <button
              onClick={() => { onSelectTool('chatbot'); onSelectConversation(null); }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-medium text-white shadow-sm transition hover:brightness-110"
              style={{ background: NTT_BLUE }}
            >
              <Plus className="w-4 h-4" /> New chat
            </button>
          </div>

          <Section title="Tools">
            {TOOLS.map((t) => {
              const active = tool === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => onSelectTool(t.id)}
                  className={`relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-medium transition ${
                    active
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-slate-100'
                      : 'text-slate-600 hover:bg-slate-200/50 dark:text-slate-400 dark:hover:bg-slate-800/50'
                  }`}
                >
                  {active && (
                    <span
                      className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full"
                      style={{ background: NTT_BLUE }}
                    />
                  )}
                  <span
                    className={active ? '' : 'text-slate-400'}
                    style={active ? { color: NTT_BLUE } : undefined}
                  >
                    {t.icon}
                  </span>
                  {t.label}
                </button>
              );
            })}
          </Section>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {pinned.length > 0 && (
              <Section title="Pinned">
                {pinned.map((c) => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === activeId}
                    onSelect={() => { onSelectTool('chatbot'); onSelectConversation(c.id); }}
                    onRename={onRename}
                    onTogglePin={onTogglePin}
                    onDelete={onDelete}
                    pinningSupported={pinningSupported}
                  />
                ))}
              </Section>
            )}

            <Section title="Chats">
              {rest.length === 0 ? (
                <p className="px-3 py-3 text-[12px] leading-relaxed text-slate-400">
                  {pinned.length > 0
                    ? 'Nothing else yet.'
                    : 'No conversations yet. Ask something to start one.'}
                </p>
              ) : (
                rest.map((c) => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === activeId}
                    onSelect={() => { onSelectTool('chatbot'); onSelectConversation(c.id); }}
                    onRename={onRename}
                    onTogglePin={onTogglePin}
                    onDelete={onDelete}
                    pinningSupported={pinningSupported}
                  />
                ))
              )}
            </Section>
          </div>
        </>
      )}

      <div className="mt-auto space-y-1 border-t border-slate-200 p-2 dark:border-slate-800">
        {footer}
      </div>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-2.5 pb-2">
      <p className="px-1 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
        {title}
      </p>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

// ── one conversation row ──────────────────────────────────────────────────────

// Typed as React.FC so `key` is accepted: this project's React types do not
// add the implicit key prop to a plain function component's inline props type.
interface RowProps {
  conversation: Conversation;
  active: boolean;
  onSelect: () => void;
  onRename: (id: string, title: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onDelete: (id: string) => void;
  pinningSupported: boolean;
}

const ConversationRow: React.FC<RowProps> = ({
  conversation: c,
  active,
  onSelect,
  onRename,
  onTogglePin,
  onDelete,
  pinningSupported,
}) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.title);
  const [menuOpen, setMenuOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const commit = () => {
    const next = draft.trim();
    // An empty title would render as a blank row with no way to select it, so
    // treat "cleared" as "cancelled" rather than saving it.
    if (next && next !== c.title) onRename(c.id, next);
    else setDraft(c.title);
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1 rounded-lg bg-white px-2 py-1 ring-1 ring-slate-300 dark:bg-slate-800 dark:ring-slate-600">
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') { setDraft(c.title); setEditing(false); }
          }}
          onBlur={commit}
          className="min-w-0 flex-1 bg-transparent py-1 text-[13px] text-slate-900 outline-none dark:text-slate-100"
        />
        <button
          onMouseDown={(e) => e.preventDefault()}
          onClick={commit}
          className="shrink-0 text-slate-400 hover:text-emerald-600"
          title="Save"
        >
          <Check className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div
      onClick={onSelect}
      className={`group relative flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-[13px] transition ${
        active
          ? 'bg-white font-medium text-slate-900 shadow-sm dark:bg-slate-800 dark:text-slate-100'
          : 'text-slate-600 hover:bg-slate-200/50 dark:text-slate-400 dark:hover:bg-slate-800/50'
      }`}
    >
      {c.pinned && (
        <Pin className="w-3 h-3 shrink-0 -rotate-45 text-slate-400" style={{ color: NTT_BLUE }} />
      )}
      <span className="min-w-0 flex-1 truncate">{c.title}</span>

      <button
        onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
        className={`shrink-0 rounded p-0.5 text-slate-400 transition hover:text-slate-700 dark:hover:text-slate-200 ${
          menuOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
        }`}
        title="More"
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>

      {menuOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={(e) => { e.stopPropagation(); setMenuOpen(false); }} />
          <div className="absolute right-1 top-full z-20 mt-0.5 w-40 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
            <MenuItem
              icon={<Pencil className="w-3.5 h-3.5" />}
              label="Rename"
              onClick={(e) => { e.stopPropagation(); setMenuOpen(false); setEditing(true); }}
            />
            {pinningSupported && (
              <MenuItem
                icon={c.pinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
                label={c.pinned ? 'Unpin' : 'Pin'}
                onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onTogglePin(c.id, !c.pinned); }}
              />
            )}
            <MenuItem
              icon={<Trash2 className="w-3.5 h-3.5" />}
              label="Delete"
              danger
              onClick={(e) => { e.stopPropagation(); setMenuOpen(false); onDelete(c.id); }}
            />
          </div>
        </>
      )}
    </div>
  );
};

function MenuItem({
  icon,
  label,
  onClick,
  danger = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: (e: React.MouseEvent) => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] transition ${
        danger
          ? 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/30'
          : 'text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800'
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
