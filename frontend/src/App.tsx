import React, { useCallback, useEffect, useState } from 'react';
import { MessageSquare, FileText, ShieldAlert, Search, Loader2 } from 'lucide-react';
import ChatbotModule from './modules/chatbot/ChatbotModule';
import ReportGeneratorModule from './modules/reports/ReportGeneratorModule';
import { useAuth } from './auth/AuthContext';
import LoginScreen from './auth/LoginScreen';
import SearchPalette from './ui/SearchPalette';
import UserMenu from './ui/UserMenu';
import { useTheme } from './ui/useTheme';
import { setActiveConversationId } from './api/chat';

// Top-level module the user is viewing. Each module owns its own internal
// sub-navigation (the report module keeps its create/list/view/edit states).
type Module = 'chatbot' | 'reports';

const NAV: { id: Module; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'chatbot', label: 'Chatbot', icon: <MessageSquare className="w-5 h-5" />, hint: 'Query incident reports' },
  { id: 'reports', label: 'Report Generator', icon: <FileText className="w-5 h-5" />, hint: 'Create & edit reports' },
];

export default function App() {
  const { user, loading, error, authEnabled, login, logout } = useAuth();
  const { isDark, toggle } = useTheme();
  const [module, setModule] = useState<Module>('chatbot');
  const [searchOpen, setSearchOpen] = useState(false);
  // Bumped when search picks a conversation, to remount the chat module so it
  // re-reads the active conversation from storage.
  const [chatKey, setChatKey] = useState(0);

  // Cmd/Ctrl-K opens search from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const openConversation = useCallback((conversationId: string) => {
    setActiveConversationId(conversationId);
    setModule('chatbot');
    setChatKey((k) => k + 1);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!user) {
    return <LoginScreen onLogin={login} error={error} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 flex">
      {/* Sidebar navigation */}
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 flex flex-col">
        <div className="flex items-center gap-2 px-5 py-5 border-b border-slate-200 dark:border-slate-800">
          <div className="p-2 bg-blue-600 text-white rounded-lg">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <div className="text-sm font-bold leading-tight">NTT Incident</div>
            <div className="text-xs text-slate-500 leading-tight">Platform</div>
          </div>
        </div>

        <div className="px-3 pt-3">
          <button
            onClick={() => setSearchOpen(true)}
            className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left text-sm text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            <Search className="w-4 h-4" />
            <span className="flex-1">Search chats</span>
            <kbd className="rounded border border-slate-200 px-1 text-[10px] dark:border-slate-600">
              ⌘K
            </kbd>
          </button>
        </div>

        <nav className="p-3 space-y-1">
          {NAV.map((item) => {
            const active = module === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setModule(item.id)}
                className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                  active
                    ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                }`}
              >
                <span className={active ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400'}>
                  {item.icon}
                </span>
                <span className="flex flex-col">
                  <span className="text-sm font-medium">{item.label}</span>
                  <span className="text-xs text-slate-400">{item.hint}</span>
                </span>
              </button>
            );
          })}
        </nav>

        {/* User menu pinned to the bottom, where account controls are expected. */}
        <div className="mt-auto border-t border-slate-200 p-2 dark:border-slate-800">
          <UserMenu
            user={user}
            onLogout={logout}
            isDark={isDark}
            onToggleTheme={toggle}
            authEnabled={authEnabled}
          />
        </div>
      </aside>

      {/* Main content: the active module.
          Chat runs full-bleed — it manages its own scrolling so the composer
          can stay pinned while the transcript moves under it. The report
          module keeps the padded page layout it was written for. */}
      <main className="flex-1 min-w-0 overflow-x-hidden">
        {module === 'chatbot' ? (
          <ChatbotModule key={chatKey} />
        ) : (
          <div className="px-4 sm:px-6 lg:px-10 py-8">
            <ReportGeneratorModule />
          </div>
        )}
      </main>

      <SearchPalette
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        onSelect={openConversation}
      />
    </div>
  );
}
