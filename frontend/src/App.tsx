import React, { useCallback, useEffect, useState } from 'react';
import { MessageSquare, FileText, Search, PanelLeftClose, PanelLeft } from 'lucide-react';
import ChatbotModule from './modules/chatbot/ChatbotModule';
import ReportGeneratorModule from './modules/reports/ReportGeneratorModule';
import { useAuth } from './auth/AuthContext';
import LoginScreen from './auth/LoginScreen';
import BootScreen from './ui/BootScreen';
import SearchPalette from './ui/SearchPalette';
import SystemStatus from './ui/SystemStatus';
import UserMenu from './ui/UserMenu';
import { ProductLockup, NttMark, NTT_BLUE } from './ui/Brand';
import { useTheme } from './ui/useTheme';
import { setActiveConversationId } from './api/chat';

// Top-level module the user is viewing. Each module owns its own internal
// sub-navigation (the report module keeps its create/list/view/edit states).
type Module = 'chatbot' | 'reports';

const NAV: { id: Module; label: string; icon: React.ReactNode }[] = [
  { id: 'chatbot', label: 'Assistant', icon: <MessageSquare className="w-[18px] h-[18px]" /> },
  { id: 'reports', label: 'Reports', icon: <FileText className="w-[18px] h-[18px]" /> },
];

const SIDEBAR_KEY = 'ntt.sidebarCollapsed';

export default function App() {
  const { user, loading, error, authEnabled, login, logout } = useAuth();
  const { isDark, toggle } = useTheme();
  const [module, setModule] = useState<Module>('chatbot');
  const [searchOpen, setSearchOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(SIDEBAR_KEY) === '1',
  );
  // Bumped when search picks a conversation, to remount the chat module so it
  // re-reads the active conversation from storage.
  const [chatKey, setChatKey] = useState(0);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((v) => !v);
      } else if (meta && e.key === '\\') {
        e.preventDefault();
        setCollapsed((v) => !v);
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

  // The boot screen covers session resolution; it enforces its own minimum
  // visible time so a fast resolve does not flash.
  if (loading) return <BootScreen done={false} />;
  if (!user) {
    return (
      <>
        <BootScreen done />
        <LoginScreen onLogin={login} error={error} />
      </>
    );
  }

  return (
    <>
      <BootScreen done />
      <div className="flex h-screen overflow-hidden bg-white text-slate-900 dark:bg-[#0a0f1a] dark:text-slate-100">
        <aside
          className={`flex shrink-0 flex-col border-r border-slate-200 bg-slate-50/70 transition-[width] duration-200 dark:border-slate-800 dark:bg-[#0d1524] ${
            collapsed ? 'w-[68px]' : 'w-[248px]'
          }`}
        >
          <div className="flex h-14 items-center justify-between px-3">
            {collapsed ? (
              <NttMark size={28} className="mx-auto" />
            ) : (
              <ProductLockup />
            )}
          </div>

          <div className="px-3 pb-2">
            <button
              onClick={() => setSearchOpen(true)}
              className={`flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-left text-[13px] text-slate-500 transition hover:border-slate-300 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400 dark:hover:border-slate-600 ${
                collapsed ? 'justify-center px-0' : ''
              }`}
              title="Search conversations (⌘K)"
            >
              <Search className="w-4 h-4 shrink-0" />
              {!collapsed && (
                <>
                  <span className="flex-1">Search</span>
                  <kbd className="rounded border border-slate-200 px-1 font-sans text-[10px] text-slate-400 dark:border-slate-600">
                    ⌘K
                  </kbd>
                </>
              )}
            </button>
          </div>

          <nav className="flex-1 space-y-0.5 px-3">
            {NAV.map((item) => {
              const active = module === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setModule(item.id)}
                  title={collapsed ? item.label : undefined}
                  className={`relative flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium transition ${
                    active
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-slate-100'
                      : 'text-slate-600 hover:bg-slate-200/50 dark:text-slate-400 dark:hover:bg-slate-800/50'
                  } ${collapsed ? 'justify-center px-0' : ''}`}
                >
                  {/* Brand-blue active rail: the one place colour marks state. */}
                  {active && (
                    <span
                      className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full"
                      style={{ background: NTT_BLUE }}
                    />
                  )}
                  <span className={active ? '' : 'text-slate-400'} style={active ? { color: NTT_BLUE } : undefined}>
                    {item.icon}
                  </span>
                  {!collapsed && <span>{item.label}</span>}
                </button>
              );
            })}
          </nav>

          <div className="space-y-1 border-t border-slate-200 p-2 dark:border-slate-800">
            {!collapsed && <SystemStatus />}
            <UserMenu
              user={user}
              onLogout={logout}
              isDark={isDark}
              onToggleTheme={toggle}
              authEnabled={authEnabled}
              collapsed={collapsed}
            />
            <button
              onClick={() => setCollapsed((v) => !v)}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-[11px] text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
              title={`${collapsed ? 'Expand' : 'Collapse'} sidebar (⌘\\)`}
            >
              {collapsed ? (
                <PanelLeft className="mx-auto w-4 h-4" />
              ) : (
                <>
                  <PanelLeftClose className="w-4 h-4" />
                  <span>Collapse</span>
                </>
              )}
            </button>
          </div>
        </aside>

        {/* Chat runs full-bleed — it manages its own scrolling so the composer
            stays pinned. The report module keeps the padded page layout it was
            written for. */}
        <main className="min-w-0 flex-1 overflow-hidden">
          {module === 'chatbot' ? (
            <ChatbotModule key={chatKey} />
          ) : (
            <div className="h-full overflow-y-auto px-4 py-8 sm:px-6 lg:px-10">
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
    </>
  );
}
