// Cmd/Ctrl-K search over chat history.
//
// Surfaces the hybrid backend search: results carry a badge saying whether the
// keyword arm, the semantic arm, or both found them. That badge is not
// decoration — when a result shares no words with the query, it is the only
// thing that explains why it is there.
//
// Snippets are server-rendered HTML from Postgres `ts_headline`, so the
// highlighted terms are the lexed ones (searching "clearing" marks "clear").
// They are injected with dangerouslySetInnerHTML, which is safe here for a
// specific reason documented at the injection site.

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Search, Loader2, MessageSquare, Sparkles, Type } from 'lucide-react';
import { searchConversations, type ConversationHit } from '../api/chat';

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (conversationId: string) => void;
}

const MATCH_LABELS: Record<ConversationHit['matched_by'], { label: string; icon: React.ReactNode }> = {
  keyword: { label: 'keyword', icon: <Type className="w-3 h-3" /> },
  semantic: { label: 'meaning', icon: <Sparkles className="w-3 h-3" /> },
  both: { label: 'keyword + meaning', icon: <Sparkles className="w-3 h-3" /> },
};

export default function SearchPalette({ open, onClose, onSelect }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ConversationHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [open]);

  // Debounced search. 200ms is short enough to feel immediate while stopping a
  // fast typist from firing a query per keystroke at Postgres.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const res = await searchConversations(q, 12);
        setResults(res.results);
        setUnavailable(!res.available);
        setActive(0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  const choose = useCallback(
    (hit: ConversationHit) => {
      onSelect(hit.conversation_id);
      onClose();
      setQuery('');
    },
    [onSelect, onClose],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') return onClose();
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && results[active]) {
      e.preventDefault();
      choose(results[active]);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 backdrop-blur-sm pt-[12vh] px-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Search conversations"
    >
      <div
        className="w-full max-w-xl rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 dark:border-slate-700">
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
          ) : (
            <Search className="w-4 h-4 text-slate-400" />
          )}
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search your conversations…"
            className="flex-1 bg-transparent py-3.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none dark:text-slate-100"
          />
          <kbd className="hidden sm:inline rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-400 dark:border-slate-700">
            esc
          </kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-2">
          {unavailable && (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              Search is unavailable on this backend.
            </p>
          )}

          {!unavailable && !loading && query.trim() && results.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              No conversations match “{query.trim()}”.
            </p>
          )}

          {!query.trim() && (
            <p className="px-3 py-6 text-center text-sm text-slate-400">
              Search by keyword or by meaning — “login loop” finds “redirect
              after SSO”.
            </p>
          )}

          <ul>
            {results.map((hit, i) => {
              const match = MATCH_LABELS[hit.matched_by];
              return (
                <li key={hit.conversation_id}>
                  <button
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(hit)}
                    className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                      i === active
                        ? 'bg-slate-100 dark:bg-slate-800'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <MessageSquare className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                      <span className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                        {hit.title}
                      </span>
                      <span className="ml-auto flex shrink-0 items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        {match.icon}
                        {match.label}
                      </span>
                    </div>
                    {hit.snippet && (
                      <p
                        className="mt-1 line-clamp-2 pl-5 text-xs text-slate-500 dark:text-slate-400"
                        // Safe: the only markup in a snippet is the <mark> tags
                        // ts_headline inserts — StartSel/StopSel are fixed in
                        // db/search.py and Postgres escapes the message text
                        // around them, so user content cannot introduce tags.
                        dangerouslySetInnerHTML={{ __html: hit.snippet }}
                      />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        {results.length > 0 && (
          <div className="flex items-center gap-3 border-t border-slate-200 px-4 py-2 text-[11px] text-slate-400 dark:border-slate-700">
            <span>↑↓ navigate</span>
            <span>↵ open</span>
            <span className="ml-auto">{results.length} conversation(s)</span>
          </div>
        )}
      </div>
    </div>
  );
}
