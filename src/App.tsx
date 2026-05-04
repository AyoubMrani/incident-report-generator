import React, { useState } from 'react';
import { ReportMetadata, ContentBlock, IncidentReport } from './types';
import { MetadataEditor } from './components/MetadataEditor';
import { BlockEditor } from './components/BlockEditor';
import { ExportPanel } from './components/ExportPanel';
import { ReportList } from './components/ReportList';
import { ReportViewer } from './components/ReportViewer';
import { FileText, Plus, List } from 'lucide-react';

type ViewState = 'create' | 'list' | 'view' | 'edit';

export default function App() {
  const [view, setView] = useState<ViewState>('create');
  const [selectedReportFile, setSelectedReportFile] = useState<string | null>(null);
  const [editingFilename, setEditingFilename] = useState<string | null>(null);

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

  const handleEditReport = async (filename: string) => {
    try {
      const response = await fetch(`/api/reports/content/${encodeURIComponent(filename)}`);
      if (!response.ok) throw new Error('Failed to load report');
      const reportData = await response.json();
      
      // Ensure all blocks have IDs (for old reports that don't have them)
      const blocksWithIds = reportData.blocks.map((block: ContentBlock) => ({
        ...block,
        id: block.id || crypto.randomUUID()
      }));
      
      // Load data into edit form
      setMetadata(reportData.metadata);
      setBlocks(blocksWithIds);
      setEditingFilename(filename);
      setView('edit');
    } catch (error) {
      console.error('Error loading report for editing:', error);
      alert('Failed to load report for editing');
    }
  };

  const handleBackFromEdit = () => {
    // Reset form
    setMetadata({
      incident_id: '',
      title: '',
      caller: '',
      category: '',
      subcategory: '',
      date: new Date().toISOString().split('T')[0],
    });
    setBlocks([]);
    setEditingFilename(null);
    setView('list');
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

              <ExportPanel report={report} editingFilename={null} />
            </div>
          )}

          {view === 'edit' && (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="flex items-center gap-3 mb-4 pb-4 border-b border-gray-200">
                <h2 className="text-xl font-bold text-gray-900">Edit Report</h2>
                <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">
                  {editingFilename}
                </span>
              </div>
              
              <MetadataEditor metadata={metadata} onChange={setMetadata} />
              
              <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                <h2 className="text-lg font-semibold mb-4 text-gray-800">Report Content</h2>
                <BlockEditor blocks={blocks} onChange={setBlocks} />
              </div>

              <div className="mt-4 mb-8 flex gap-2">
                <button
                  onClick={handleBackFromEdit}
                  className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 transition-colors"
                >
                  Cancel
                </button>
              </div>

              <ExportPanel report={report} editingFilename={editingFilename} />
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
                onEdit={handleEditReport}
              />
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
