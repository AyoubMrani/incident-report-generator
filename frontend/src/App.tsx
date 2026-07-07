import React, { useState } from 'react';
import { MessageSquare, FileText, ShieldAlert } from 'lucide-react';
import ChatbotModule from './modules/chatbot/ChatbotModule';
import ReportGeneratorModule from './modules/reports/ReportGeneratorModule';

// Top-level module the user is viewing. Each module owns its own internal
// sub-navigation (the report module keeps its create/list/view/edit states).
type Module = 'chatbot' | 'reports';

const NAV: { id: Module; label: string; icon: React.ReactNode; hint: string }[] = [
  { id: 'chatbot', label: 'Chatbot', icon: <MessageSquare className="w-5 h-5" />, hint: 'Query incident reports' },
  { id: 'reports', label: 'Report Generator', icon: <FileText className="w-5 h-5" />, hint: 'Create & edit reports' },
];

export default function App() {
  const [module, setModule] = useState<Module>('chatbot');

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 flex">
      {/* Sidebar navigation */}
      <aside className="w-64 shrink-0 border-r border-gray-200 bg-white flex flex-col">
        <div className="flex items-center gap-2 px-5 py-5 border-b border-gray-200">
          <div className="p-2 bg-blue-600 text-white rounded-lg">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <div className="text-sm font-bold leading-tight">NTT Incident</div>
            <div className="text-xs text-gray-500 leading-tight">Platform</div>
          </div>
        </div>

        <nav className="p-3 space-y-1">
          {NAV.map((item) => {
            const active = module === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setModule(item.id)}
                className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                  active ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`}
              >
                <span className={active ? 'text-blue-600' : 'text-gray-400'}>{item.icon}</span>
                <span className="flex flex-col">
                  <span className="text-sm font-medium">{item.label}</span>
                  <span className="text-xs text-gray-400">{item.hint}</span>
                </span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Main content: the active module */}
      <main className="flex-1 min-w-0 px-4 sm:px-6 lg:px-10 py-8 overflow-x-hidden">
        {module === 'chatbot' ? <ChatbotModule /> : <ReportGeneratorModule />}
      </main>
    </div>
  );
}
