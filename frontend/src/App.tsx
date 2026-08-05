import React, { useCallback, useEffect, useState } from 'react';
import ChatbotModule from './modules/chatbot/ChatbotModule';
import ReportGeneratorModule from './modules/reports/ReportGeneratorModule';
import { useAuth } from './auth/AuthContext';
import LoginScreen from './auth/LoginScreen';
import BootScreen from './ui/BootScreen';
import MetricsPanel from './ui/MetricsPanel';
import ProfileDialog from './ui/ProfileDialog';
import SearchPalette from './ui/SearchPalette';
import SettingsDialog, { loadPrefs, type Preferences } from './ui/SettingsDialog';
import Sidebar, { type Tool } from './ui/Sidebar';
import SystemStatus from './ui/SystemStatus';
import UserMenu from './ui/UserMenu';
import { useTheme } from './ui/useTheme';
import { useToast } from './ui/Toast';
import {
  deleteConversation,
  listConversations,
  pinConversation,
  renameConversation,
  setActiveConversationId,
  getActiveConversationId,
  type Conversation,
} from './api/chat';

const SIDEBAR_KEY = 'ntt.sidebarCollapsed';

export default function App() {
  const { user, loading, error, authEnabled, login, logout, setUser } = useAuth();
  const { theme, setTheme, isDark, toggle } = useTheme();
  const toast = useToast();

  const [tool, setTool] = useState<Tool>('chatbot');
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const [prefs, setPrefs] = useState<Preferences>(loadPrefs);
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(SIDEBAR_KEY) === '1',
  );

  // Conversation state lives here, not in the chat module: the sidebar renders
  // the list and the module renders the transcript, so the single owner has to
  // be their common parent.
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(getActiveConversationId());
  const [pinningSupported, setPinningSupported] = useState(true);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch {
      /* store may be empty or unreachable; the sidebar shows its empty state */
    }
  }, []);

  useEffect(() => {
    if (user) void refreshConversations();
  }, [user, refreshConversations]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((v) => !v);
      } else if (meta && e.key === '\\') {
        e.preventDefault();
        setCollapsed((v) => !v);
      } else if (meta && e.key === ',') {
        e.preventDefault();
        setSettingsOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const selectConversation = useCallback((id: string | null) => {
    setActiveConversationId(id);
    setActiveId(id);
  }, []);

  const openConversation = useCallback((id: string) => {
    selectConversation(id);
    setTool('chatbot');
  }, [selectConversation]);

  const handleRename = useCallback(async (id: string, title: string) => {
    // Optimistic: renaming is a local, reversible edit, and waiting on the
    // round trip makes the sidebar feel laggy on every keystroke-to-commit.
    setConversations((list) =>
      list.map((c) => (c.id === id ? { ...c, title } : c)),
    );
    try {
      await renameConversation(id, title);
    } catch {
      toast.error('Could not rename the conversation.');
      void refreshConversations();
    }
  }, [toast, refreshConversations]);

  const handleTogglePin = useCallback(async (id: string, pinned: boolean) => {
    setConversations((list) =>
      list.map((c) => (c.id === id ? { ...c, pinned } : c)),
    );
    try {
      const ok = await pinConversation(id, pinned);
      if (!ok) {
        // Backend has no pinning (SQLite fallback): hide the control rather
        // than leaving one that silently does nothing.
        setPinningSupported(false);
        void refreshConversations();
        return;
      }
      void refreshConversations();
    } catch {
      toast.error('Could not update the pin.');
      void refreshConversations();
    }
  }, [toast, refreshConversations]);

  const handleDelete = useCallback(async (id: string) => {
    setConversations((list) => list.filter((c) => c.id !== id));
    if (id === activeId) selectConversation(null);
    try {
      await deleteConversation(id);
    } catch {
      toast.error('Could not delete the conversation.');
      void refreshConversations();
    }
  }, [activeId, selectConversation, toast, refreshConversations]);

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
      <div className="flex h-screen overflow-hidden bg-app text-app">
        <Sidebar
          collapsed={collapsed}
          onToggleCollapsed={() => setCollapsed((v) => !v)}
          onOpenSearch={() => setSearchOpen(true)}
          tool={tool}
          onSelectTool={setTool}
          conversations={conversations}
          activeId={activeId}
          onSelectConversation={selectConversation}
          onRename={handleRename}
          onTogglePin={handleTogglePin}
          onDelete={handleDelete}
          pinningSupported={pinningSupported}
          footer={
            <>
              {!collapsed && <SystemStatus />}
              <UserMenu
                user={user}
                onLogout={logout}
                isDark={isDark}
                onToggleTheme={toggle}
                authEnabled={authEnabled}
                collapsed={collapsed}
                onOpenProfile={() => setProfileOpen(true)}
                onOpenSettings={() => setSettingsOpen(true)}
                onOpenMetrics={user.is_admin ? () => setMetricsOpen(true) : undefined}
              />
            </>
          }
        />

        {/* Chat runs full-bleed — it manages its own scrolling so the composer
            stays pinned. The report module keeps the padded page layout it was
            written for. */}
        <main className="min-w-0 flex-1 overflow-hidden">
          {tool === 'chatbot' ? (
            <ChatbotModule
              activeId={activeId}
              onSelectConversation={selectConversation}
              onConversationsChanged={refreshConversations}
              prefs={prefs}
            />
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

        <MetricsPanel open={metricsOpen} onClose={() => setMetricsOpen(false)} />

        <SettingsDialog
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          theme={theme}
          onSelectTheme={setTheme}
          prefs={prefs}
          onChangePrefs={setPrefs}
        />

        <ProfileDialog
          open={profileOpen}
          onClose={() => setProfileOpen(false)}
          initialName={user.display_name || user.username}
          initialAvatar={user.avatar_url ?? ''}
          onSaved={(p) =>
            setUser({ ...user, display_name: p.display_name, avatar_url: p.avatar_url })
          }
        />
      </div>
    </>
  );
}
