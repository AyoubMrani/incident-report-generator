import React, { useState } from 'react';
import { ReportMetadata, ContentBlock, IncidentReport, StoredMetadataField } from '../../types';
import { MetadataEditor } from './components/MetadataEditor';
import { BlockEditor } from './components/BlockEditor';
import { ExportPanel } from './components/ExportPanel';
import { ReportList } from './components/ReportList';
import { ReportViewer } from './components/ReportViewer';
import { FileText, Plus, List } from 'lucide-react';
import { apiFetch } from '../../api/chat';
import { useToast } from '../../ui/Toast';
import { NTT_BLUE } from '../../ui/Brand';

type ViewState = 'create' | 'list' | 'view' | 'edit';

const EMPTY_METADATA: ReportMetadata = {
  incident_id: '',
  title: '',
  caller: '',
  category: '',
  subcategory: '',
  date: new Date().toISOString().split('T')[0],
};

export default function ReportGeneratorModule() {
  const [view, setView] = useState<ViewState>('create');
  const [selectedReportFile, setSelectedReportFile] = useState<string | null>(null);
  const [editingFilename, setEditingFilename] = useState<string | null>(null);
  const [reportCustomFields, setReportCustomFields] = useState<StoredMetadataField[]>([]);
  const [metadata, setMetadata] = useState<ReportMetadata>(EMPTY_METADATA);
  const [blocks, setBlocks] = useState<ContentBlock[]>([]);
  const toast = useToast();

  const report: IncidentReport = { metadata, blocks };

  const handleSelectReport = (filename: string) => {
    setSelectedReportFile(filename);
    setView('view');
  };

  const handleEditReport = async (filename: string) => {
    try {
      const response = await apiFetch(`/api/reports/content/${encodeURIComponent(filename)}`);

      if (response.status === 404) {
        toast.error('Report not found — it may have been deleted. Refresh the list.');
        return;
      }
      if (response.status === 401 || response.status === 403) {
        toast.error('You do not have permission to edit this report.');
        return;
      }
      if (!response.ok) throw new Error('Failed to load report');
      const reportData = await response.json();

      // Ensure all blocks have IDs (for old reports that don't have them)
      const blocksWithIds = reportData.blocks.map((block: ContentBlock) => ({
        ...block,
        id: block.id || crypto.randomUUID(),
      }));

      // Extract custom fields from report metadata (any fields not in the standard set)
      const standardMetadataKeys = new Set(['incident_id', 'title', 'caller', 'category', 'subcategory', 'date']);
      const customFieldsFromReport: StoredMetadataField[] = Object.keys(reportData.metadata)
        .filter((key) => !standardMetadataKeys.has(key))
        .map((key) => ({ id: key, name: key, label: key }));

      setMetadata(reportData.metadata);
      setBlocks(blocksWithIds);
      setReportCustomFields(customFieldsFromReport);
      setEditingFilename(filename);
      setView('edit');
    } catch (error) {
      console.error('Error loading report for editing:', error);
      toast.error('Failed to load report for editing.');
    }
  };

  const handleBackFromEdit = () => {
    setMetadata(EMPTY_METADATA);
    setBlocks([]);
    setReportCustomFields([]);
    setEditingFilename(null);
    setView('list');
  };

  const TABS: { id: Extract<ViewState, 'create' | 'list'>; label: string; icon: React.ReactNode }[] = [
    { id: 'create', label: 'Create New', icon: <Plus className="w-4 h-4" /> },
    { id: 'list', label: 'View Reports', icon: <List className="w-4 h-4" /> },
  ];

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white shadow-sm"
            style={{ background: NTT_BLUE }}
          >
            <FileText className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-app text-xl font-semibold tracking-tight">
              Incident Report Generator
            </h1>
            <p className="text-app-muted text-sm">
              Create structured, AI-ready incident reports
            </p>
          </div>
        </div>

        <div className="bg-app-surface border-app inline-flex rounded-lg border p-1">
          {TABS.map((t) => {
            const active = view === t.id || (t.id === 'list' && view === 'view');
            return (
              <button
                key={t.id}
                onClick={() => setView(t.id)}
                className={`flex items-center gap-2 rounded-md px-3.5 py-1.5 text-[13px] font-medium transition-colors ${
                  active
                    ? 'bg-app-elevated text-app shadow-sm'
                    : 'text-app-muted hover:text-app'
                }`}
                style={active ? { color: NTT_BLUE } : undefined}
              >
                {t.icon}
                {t.label}
              </button>
            );
          })}
        </div>
      </header>

      <main className="pb-16">
        {view === 'create' && (
          <div className="ntt-rise space-y-6">
            <MetadataEditor metadata={metadata} onChange={setMetadata} />

            <div className="bg-app-elevated border-app rounded-xl border p-6 shadow-sm">
              <h2 className="text-app mb-4 text-[15px] font-semibold">Report Content</h2>
              <BlockEditor blocks={blocks} onChange={setBlocks} />
            </div>

            <ExportPanel report={report} editingFilename={null} />
          </div>
        )}

        {view === 'edit' && (
          <div className="ntt-rise space-y-6">
            <div className="border-app flex items-center gap-3 border-b pb-4">
              <h2 className="text-app text-lg font-semibold">Edit Report</h2>
              <span
                className="rounded px-2 py-1 font-mono text-[11px]"
                style={{ background: `${NTT_BLUE}14`, color: NTT_BLUE }}
              >
                {editingFilename}
              </span>
            </div>

            <MetadataEditor metadata={metadata} onChange={setMetadata} reportCustomFields={reportCustomFields} />

            <div className="bg-app-elevated border-app rounded-xl border p-6 shadow-sm">
              <h2 className="text-app mb-4 text-[15px] font-semibold">Report Content</h2>
              <BlockEditor blocks={blocks} onChange={setBlocks} />
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleBackFromEdit}
                className="bg-app-surface text-app hover:bg-app-hover border-app rounded-lg border px-4 py-2 text-sm font-medium transition"
              >
                Cancel
              </button>
            </div>

            <ExportPanel report={report} editingFilename={editingFilename} />
          </div>
        )}

        {view === 'list' && (
          <div className="ntt-rise">
            <ReportList onSelectReport={handleSelectReport} />
          </div>
        )}

        {view === 'view' && selectedReportFile && (
          <div className="ntt-rise">
            <ReportViewer
              filename={selectedReportFile}
              onBack={() => setView('list')}
              onEdit={handleEditReport}
            />
          </div>
        )}
      </main>
    </div>
  );
}
