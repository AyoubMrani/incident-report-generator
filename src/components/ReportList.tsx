import React, { useEffect, useState, useMemo } from 'react';
import { ReportMetadata } from '../types';
import { FileText, Calendar, User, Tag, Loader2, Eye, Trash2, Search, X } from 'lucide-react';
import Swal from 'sweetalert2';

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
    try {
      const response = await fetch('/api/reports');
      if (!response.ok) throw new Error('Failed to fetch reports');
      const data = await response.json();
      setReports(data.reports || []);
    } catch (err) {
      setError('Could not load reports. Make sure the server is running.');
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleDeleteReport = async (filename: string) => {
    // Extract incident_id from simple filename "incident_inc0001_timestamp.json"
    const incidentMatch = filename.match(/incident_([^_]+)_/);
    const incident_id = incidentMatch ? incidentMatch[1] : null;

    if (!incident_id) {
      await Swal.fire({
        title: 'Error!',
        text: 'Could not determine incident ID.',
        icon: 'error',
      });
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

    if (!result.isConfirmed) {
      return;
    }

    setDeletingFilename(filename);
    try {
      const response = await fetch(`/api/delete?incident_id=${encodeURIComponent(incident_id)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete report');
      
      // Refresh the list
      await fetchReports();
      
      await Swal.fire({
        title: 'Deleted!',
        text: 'Report has been deleted.',
        icon: 'success',
        timer: 1500,
      });
    } catch (err) {
      setError('Could not delete report.');
      console.error(err);
      await Swal.fire({
        title: 'Error!',
        text: 'Failed to delete report.',
        icon: 'error',
      });
    } finally {
      setDeletingFilename(null);
    }
  };

  // Get unique categories from all reports
  const uniqueCategories = useMemo(() => {
    const categories = new Set<string>();
    reports.forEach(r => {
      if (r.metadata.category) {
        categories.add(r.metadata.category);
      }
    });
    return Array.from(categories).sort();
  }, [reports]);

  // Filter reports based on search query, category, and date range
  const filteredReports = useMemo(() => {
    let filtered = [...reports];

    // Search filter - searches across incident_id, title, caller, category
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(report => {
        const incident_id = (report.metadata.incident_id || '').toLowerCase();
        const title = (report.metadata.title || '').toLowerCase();
        const caller = (report.metadata.caller || '').toLowerCase();
        const category = (report.metadata.category || '').toLowerCase();
        return incident_id.includes(query) || title.includes(query) || caller.includes(query) || category.includes(query);
      });
    }

    // Category filter
    if (filterCategory) {
      filtered = filtered.filter(report => report.metadata.category === filterCategory);
    }

    // Date range filter
    if (filterDateRange !== 'all') {
      const now = Date.now();
      let daysAgo: number;
      switch (filterDateRange) {
        case '7days':
          daysAgo = 7;
          break;
        case '30days':
          daysAgo = 30;
          break;
        case '90days':
          daysAgo = 90;
          break;
        default:
          daysAgo = 0;
      }
      const cutoffTime = now - daysAgo * 24 * 60 * 60 * 1000;
      filtered = filtered.filter(report => report.timestamp >= cutoffTime);
    }

    return filtered;
  }, [reports, searchQuery, filterCategory, filterDateRange]);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-red-50 text-red-700 rounded-lg border border-red-200">
        {error}
      </div>
    );
  }

  if (reports.length === 0) {
    return (
      <div className="text-center p-12 bg-white rounded-lg shadow-sm border border-gray-200">
        <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900">No reports found</h3>
        <p className="text-gray-500 mt-1">Create and save a report to see it listed here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Search and Filter Bar */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 space-y-4">
        {/* Search Input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search by ID, title, caller, or category..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Filter Options */}
        <div className="flex flex-wrap gap-3">
          {/* Category Filter */}
          {uniqueCategories.length > 0 && (
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500 bg-white"
            >
              <option value="">All Categories</option>
              {uniqueCategories.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          )}

          {/* Date Range Filter */}
          <select
            value={filterDateRange}
            onChange={(e) => setFilterDateRange(e.target.value as 'all' | '7days' | '30days' | '90days')}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500 bg-white"
          >
            <option value="all">All Time</option>
            <option value="7days">Last 7 Days</option>
            <option value="30days">Last 30 Days</option>
            <option value="90days">Last 90 Days</option>
          </select>

          {/* Clear All Filters */}
          {(searchQuery || filterCategory || filterDateRange !== 'all') && (
            <button
              onClick={() => {
                setSearchQuery('');
                setFilterCategory('');
                setFilterDateRange('all');
              }}
              className="px-3 py-2 bg-gray-100 text-gray-700 hover:bg-gray-200 rounded-md text-sm transition-colors"
            >
              Clear All
            </button>
          )}
        </div>

        {/* Results Count */}
        <div className="text-sm text-gray-600">
          Showing {filteredReports.length} of {reports.length} report{reports.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Reports List */}
      {filteredReports.length === 0 ? (
        <div className="text-center p-8 bg-white rounded-lg shadow-sm border border-gray-200">
          <FileText className="w-8 h-8 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500">No reports match your search or filters.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredReports.map((report) => (
            <div
              key={report.filename}
              className="bg-white p-5 rounded-lg shadow-sm border border-gray-200 hover:border-blue-300 transition-colors flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4"
            >
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs font-mono rounded">
                    {report.metadata.incident_id || 'No ID'}
                  </span>
                  <h3 className="text-lg font-semibold text-gray-900">
                    {report.metadata.title || 'Untitled Report'}
                  </h3>
                </div>
                
                <div className="flex flex-wrap gap-4 text-sm text-gray-500 mt-2">
                  <div className="flex items-center gap-1">
                    <Calendar className="w-4 h-4" />
                    {new Date(report.timestamp).toLocaleDateString()}
                  </div>
                  {report.metadata.caller && (
                    <div className="flex items-center gap-1">
                      <User className="w-4 h-4" />
                      {report.metadata.caller}
                    </div>
                  )}
                  {report.metadata.category && (
                    <div className="flex items-center gap-1">
                      <Tag className="w-4 h-4" />
                      {report.metadata.category}
                    </div>
                  )}
                </div>
              </div>
              
              <div className="flex gap-2">
                <button
                  onClick={() => onSelectReport(report.filename)}
                  className="flex items-center px-4 py-2 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-md transition-colors whitespace-nowrap"
                >
                  <Eye className="w-4 h-4 mr-2" />
                  View Report
                </button>
                <button
                  onClick={() => handleDeleteReport(report.filename)}
                  disabled={deletingFilename === report.filename}
                  className="flex items-center px-3 py-2 bg-red-50 text-red-700 hover:bg-red-100 rounded-md transition-colors whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Delete this report"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}