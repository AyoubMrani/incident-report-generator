import React, { useEffect, useState } from 'react';
import { ReportMetadata } from '../types';
import { FileText, Calendar, User, Tag, Loader2, Eye, Trash2 } from 'lucide-react';
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
      const response = await fetch(`/api/delete?filename=${encodeURIComponent(filename)}`, {
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
      {reports.map((report) => (
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
  );
}