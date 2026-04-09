import React, { useState } from 'react';
import { ReportMetadata, ContentBlock, IncidentReport } from './types';
import { MetadataEditor } from './components/MetadataEditor';
import { BlockEditor } from './components/BlockEditor';
import { ExportPanel } from './components/ExportPanel';
import { ReportList } from './components/ReportList';
import { ReportViewer } from './components/ReportViewer';
import { FileText, Plus, List } from 'lucide-react';

type ViewState = 'create' | 'list' | 'view';

export default function App() {
  const [view, setView] = useState<ViewState>('create');
  const [selectedReportFile, setSelectedReportFile] = useState<string | null>(null);

  const [metadata, setMetadata] = useState<ReportMetadata>({
    incident_id: '',
    title: '',
    caller: '',
    category: '',
    subcategory: '',
    date: new Date().toISOString().split('T')[0],
  });

  const [blocks, setBlocks] = useState<ContentBlock[]>([]);

  const report: IncidentReport = {
    metadata,
    blocks,
  };

  const handleSelectReport = (filename: string) => {
    setSelectedReportFile(filename);
    setView('view');
  };

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        <header className="mb-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-600 text-white rounded-lg shadow-sm">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Incident Report Generator</h1>
              <p className="text-sm text-gray-500">Create structured, AI-ready incident reports</p>
            </div>
          </div>
          
          <div className="flex bg-gray-200 p-1 rounded-lg">
            <button
              onClick={() => setView('create')}
              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                view === 'create' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <Plus className="w-4 h-4 mr-2" />
              Create New
            </button>
            <button
              onClick={() => setView('list')}
              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                view === 'list' || view === 'view' ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <List className="w-4 h-4 mr-2" />
              View Reports
            </button>
          </div>
        </header>

        <main>
          {view === 'create' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              <MetadataEditor metadata={metadata} onChange={setMetadata} />
              
              <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h2 className="text-lg font-semibold mb-4 text-gray-800">Report Content</h2>
                <BlockEditor blocks={blocks} onChange={setBlocks} />
              </div>

              <ExportPanel report={report} />
            </div>
          )}

          {view === 'list' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              <ReportList onSelectReport={handleSelectReport} />
            </div>
          )}

          {view === 'view' && selectedReportFile && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              <ReportViewer 
                filename={selectedReportFile} 
                onBack={() => setView('list')} 
              />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
