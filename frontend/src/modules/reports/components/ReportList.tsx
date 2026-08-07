import React, { useEffect, useState, useMemo } from 'react';
import { ReportMetadata } from '../../../types';
import { FileText, Calendar, User, Tag, Loader2, Eye, Trash2, Search, X, AlertTriangle } from 'lucide-react';
import Swal from 'sweetalert2';
import { apiFetch } from '../../../api/chat';
import { NTT_BLUE } from '../../../ui/Brand';

interface ReportSummary {
  filename: string;
  metadata: ReportMetadata;
  timestamp: number;
}

interface Props {
  onSelectReport: (filename: string) => void;
}

export function ReportList({ onSelectReport }: Props) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingFilename, setDeletingFilename] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('');
  const [filterDateRange, setFilterDateRange] = useState<'all' | '7days' | '30days' | '90days'>('all');

  const fetchReports = async () => {
    setError(null);
    try {
      const response = await apiFetch('/api/reports');
      // Auth failures get their own message: "server not running" is the wrong
      // diagnosis for "you are not signed in" or "your session expired", and
      // sent someone chasing the backend for a token problem.
      if (response.status === 401) {
        setError('Your session has expired. Sign in again to view reports.');
        return;
      }
      if (response.status === 403) {
        setError('Your account does not have permission to view reports.');
        return;
      }
      if (!response.ok) throw new Error(`Request failed (${response.status})`);
      const data = await response.json();
      setReports(data.reports || []);
    } catch (err) {
      setError('Could not reach the server. Check your connection and try again.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleDeleteReport = async (filename: string) => {
    const incidentMatch = filename.match(/incident_([^_]+)_/);
    const incident_id = incidentMatch ? incidentMatch[1] : null;

    if (!incident_id) {
      await Swal.fire({ title: 'Error!', text: 'Could not determine incident ID.', icon: 'error' });
      return;
    }

    const result = await Swal.fire({
      title: 'Delete Report?',
      text: 'This action cannot be undone.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#ef4444',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Delete',
      cancelButtonText: 'Cancel',
    });
    if (!result.isConfirmed) return;

    setDeletingFilename(filename);
    try {
      const response = await apiFetch(`/api/delete?incident_id=${encodeURIComponent(incident_id)}`, {
        method: 'DELETE',
      });
      if (response.status === 403) {
        await Swal.fire({ title: 'Not allowed', text: 'Your account has read-only access.', icon: 'error' });
        return;
      }
      if (!response.ok) throw new Error('Failed to delete report');

      await fetchReports();
      await Swal.fire({ title: 'Deleted!', text: 'Report has been deleted.', icon: 'success', timer: 1500 });
    } catch (err) {
      console.error(err);
      await Swal.fire({ title: 'Error!', text: 'Failed to delete report.', icon: 'error' });
    } finally {
      setDeletingFilename(null);
    }
  };

  const uniqueCategories = useMemo(() => {
    const categories = new Set<string>();
    reports.forEach((r) => { if (r.metadata.category) categories.add(r.metadata.category); });
    return Array.from(categories).sort();
  }, [reports]);

  const filteredReports = useMemo(() => {
    let filtered = [...reports];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((report) => {
        const incident_id = (report.metadata.incident_id || '').toLowerCase();
        const title = (report.metadata.title || '').toLowerCase();
        const caller = (report.metadata.caller || '').toLowerCase();
        const category = (report.metadata.category || '').toLowerCase();
        return incident_id.includes(query) || title.includes(query) || caller.includes(query) || category.includes(query);
      });
    }
    if (filterCategory) {
      filtered = filtered.filter((report) => report.metadata.category === filterCategory);
    }
    if (filterDateRange !== 'all') {
      const daysAgo = { '7days': 7, '30days': 30, '90days': 90 }[filterDateRange];
      const cutoffTime = Date.now() - daysAgo * 24 * 60 * 60 * 1000;
      filtered = filtered.filter((report) => report.timestamp >= cutoffTime);
    }
    return filtered;
  }, [reports, searchQuery, filterCategory, filterDateRange]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-6 h-6 animate-spin" style={{ color: NTT_BLUE }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-5 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
        <AlertTriangle className="mt-0.5 w-5 h-5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm">{error}</p>
          <button
            onClick={() => { setIsLoading(true); fetchReports(); }}
            className="mt-2 text-sm font-medium underline underline-offset-2"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="bg-app-elevated border-app rounded-xl border p-12 text-center shadow-sm">
        <FileText className="text-app-muted mx-auto mb-4 h-12 w-12 opacity-40" />
        <h3 className="text-app text-[15px] font-medium">No reports found</h3>
        <p className="text-app-muted mt-1 text-sm">Create and save a report to see it listed here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-app-elevated border-app space-y-4 rounded-xl border p-4 shadow-sm">
        <div className="relative">
          <Search className="text-app-muted absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by ID, title, caller, or category…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="border-app bg-app text-app w-full rounded-lg border py-2 pl-9 pr-9 text-sm outline-none transition focus:border-app-strong"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="text-app-muted hover:text-app absolute right-3 top-1/2 -translate-y-1/2 transition"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {uniqueCategories.length > 0 && (
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="border-app bg-app text-app rounded-lg border px-3 py-2 text-[13px] outline-none"
            >
              <option value="">All Categories</option>
              {uniqueCategories.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
            </select>
          )}

          <select
            value={filterDateRange}
            onChange={(e) => setFilterDateRange(e.target.value as typeof filterDateRange)}
            className="border-app bg-app text-app rounded-lg border px-3 py-2 text-[13px] outline-none"
          >
            <option value="all">All Time</option>
            <option value="7days">Last 7 Days</option>
            <option value="30days">Last 30 Days</option>
            <option value="90days">Last 90 Days</option>
          </select>

          {(searchQuery || filterCategory || filterDateRange !== 'all') && (
            <button
              onClick={() => { setSearchQuery(''); setFilterCategory(''); setFilterDateRange('all'); }}
              className="bg-app-hover text-app hover:bg-app-hover rounded-lg px-3 py-2 text-[13px] transition"
            >
              Clear All
            </button>
          )}

          <span className="text-app-muted ml-auto text-[13px]">
            {filteredReports.length} of {reports.length} report{reports.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {filteredReports.length === 0 ? (
        <div className="bg-app-elevated border-app rounded-xl border p-8 text-center shadow-sm">
          <FileText className="text-app-muted mx-auto mb-3 h-8 w-8 opacity-40" />
          <p className="text-app-muted text-sm">No reports match your search or filters.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredReports.map((report) => (
            <div
              key={report.filename}
              className="bg-app-elevated border-app hover:border-app-strong flex flex-col items-start gap-4 rounded-xl border p-4 shadow-sm transition sm:flex-row sm:items-center"
            >
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="bg-app-hover text-app-muted rounded px-2 py-0.5 font-mono text-[11px]">
                    {report.metadata.incident_id || 'No ID'}
                  </span>
                  <h3 className="text-app truncate text-[15px] font-semibold">
                    {report.metadata.title || 'Untitled Report'}
                  </h3>
                </div>
                <div className="text-app-muted mt-2 flex flex-wrap gap-4 text-[13px]">
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5" />
                    {new Date(report.timestamp).toLocaleDateString()}
                  </span>
                  {report.metadata.caller && (
                    <span className="flex items-center gap-1">
                      <User className="h-3.5 w-3.5" />
                      {report.metadata.caller}
                    </span>
                  )}
                  {report.metadata.category && (
                    <span className="flex items-center gap-1">
                      <Tag className="h-3.5 w-3.5" />
                      {report.metadata.category}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => onSelectReport(report.filename)}
                  className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3.5 py-2 text-[13px] font-medium transition"
                  style={{ background: `${NTT_BLUE}14`, color: NTT_BLUE }}
                >
                  <Eye className="h-4 w-4" />
                  View Report
                </button>
                <button
                  onClick={() => handleDeleteReport(report.filename)}
                  disabled={deletingFilename === report.filename}
                  className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-950/50"
                  title="Delete this report"
                >
                  {deletingFilename === report.filename ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
