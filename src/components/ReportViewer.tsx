import React, { useEffect, useState } from 'react';
import { IncidentReport } from '../types';
import { Loader2, ArrowLeft, Download, FileJson, FileText, Trash2 } from 'lucide-react';
import Swal from 'sweetalert2';

interface Props {
  filename: string;
  onBack: () => void;
}

export function ReportViewer({ filename, onBack }: Props) {
  const [report, setReport] = useState<IncidentReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDeleteReport = async () => {
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

    setIsDeleting(true);
    try {
      const response = await fetch(`/api/delete?filename=${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete report');
      
      await Swal.fire({
        title: 'Deleted!',
        text: 'Report has been deleted.',
        icon: 'success',
        timer: 1500,
      });
      
      // Go back to list after deletion
      onBack();
    } catch (err) {
      setError('Could not delete report.');
      console.error(err);
      await Swal.fire({
        title: 'Error!',
        text: 'Failed to delete report.',
        icon: 'error',
      });
      setIsDeleting(false);
    }
  };

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const response = await fetch(`/api/reports-content?filename=${encodeURIComponent(filename)}`);
        if (!response.ok) throw new Error('Failed to fetch report content');
        const data = await response.json();
        setReport(data);
      } catch (err) {
        setError('Could not load report content.');
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchReport();
  }, [filename]);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center p-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="p-6 bg-red-50 text-red-700 rounded-lg border border-red-200">
        {error || 'Report not found'}
        <button onClick={onBack} className="block mt-4 text-red-800 underline">Go Back</button>
      </div>
    );
  }

  const metadata = report?.metadata || {};
  const blocks = report?.blocks || [];
  const mdFilename = filename.replace('.json', '.md');

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <div className="bg-gray-50 border-b border-gray-200 p-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <button 
          onClick={onBack}
          className="flex items-center text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="w-4 h-4 mr-1" />
          Back to List
        </button>
        <div className="flex gap-2">
          <a 
            href={`/api/download?filename=${encodeURIComponent(filename)}`}
            download
            className="flex items-center px-3 py-1.5 bg-gray-200 text-gray-700 hover:bg-gray-300 rounded text-sm transition-colors"
          >
            <FileJson className="w-4 h-4 mr-1.5" />
            JSON
          </a>
          <a 
            href={`/api/download?filename=${encodeURIComponent(mdFilename)}`}
            download
            className="flex items-center px-3 py-1.5 bg-gray-200 text-gray-700 hover:bg-gray-300 rounded text-sm transition-colors"
          >
            <FileText className="w-4 h-4 mr-1.5" />
            Markdown
          </a>
          <a 
            href={`/api/html?filename=${encodeURIComponent(filename)}`}
            download
            className="flex items-center px-3 py-1.5 bg-green-100 text-green-700 hover:bg-green-200 rounded text-sm transition-colors"
            title="Download as HTML with embedded images"
          >
            <FileText className="w-4 h-4 mr-1.5" />
            HTML
          </a>
          <button
            onClick={handleDeleteReport}
            disabled={isDeleting}
            className="flex items-center px-3 py-1.5 bg-red-100 text-red-700 hover:bg-red-200 rounded text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Delete this report"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="p-6 sm:p-8">
        {/* Metadata Header */}
        <div className="mb-8 pb-6 border-b border-gray-100">
          <div className="flex items-center gap-3 mb-2">
            <span className="px-2.5 py-1 bg-blue-100 text-blue-800 text-sm font-mono rounded-md">
              {metadata.incident_id || 'No ID'}
            </span>
            <span className="text-gray-500 text-sm">{metadata.date}</span>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-4">{metadata.title || 'Untitled Report'}</h1>
          
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-4 gap-x-8 text-sm">
            <div>
              <span className="block text-gray-500 mb-1">Caller</span>
              <span className="font-medium text-gray-900">{metadata.caller || '-'}</span>
            </div>
            <div>
              <span className="block text-gray-500 mb-1">Category</span>
              <span className="font-medium text-gray-900">{metadata.category || '-'}</span>
            </div>
            <div>
              <span className="block text-gray-500 mb-1">Subcategory</span>
              <span className="font-medium text-gray-900">{metadata.subcategory || '-'}</span>
            </div>
          </div>
        </div>

        {/* Content Blocks */}
        <div className="space-y-6 text-gray-800">
          {blocks.map((block, index) => {
            switch (block.type) {
              case 'heading':
                const sizeClass = block.level === 1 ? 'text-2xl mt-8 mb-4' : 
                                  block.level === 2 ? 'text-xl mt-6 mb-3' : 
                                  block.level === 3 ? 'text-lg mt-4 mb-2' : 'text-base mt-4 mb-2';
                const className = `font-bold text-gray-900 ${sizeClass}`;
                if (block.level === 1) return <h1 key={index} className={className}>{block.content}</h1>;
                if (block.level === 2) return <h2 key={index} className={className}>{block.content}</h2>;
                if (block.level === 3) return <h3 key={index} className={className}>{block.content}</h3>;
                return <h4 key={index} className={className}>{block.content}</h4>;
              
              case 'paragraph':
                return <p key={index} className="leading-relaxed">{block.content}</p>;
              
              case 'list':
                const ListTag = block.ordered ? 'ol' : 'ul';
                const listClass = block.ordered ? 'list-decimal' : 'list-disc';
                return (
                  <ListTag key={index} className={`${listClass} pl-5 space-y-1`}>
                    {block.items.map((item, i) => <li key={i}>{item}</li>)}
                  </ListTag>
                );
              
              case 'incident_example':
                return (
                  <div key={index} className="bg-blue-50 p-4 rounded-md border border-blue-100 my-4">
                    <span className="font-semibold text-blue-900">Incident example: </span>
                    <span className="text-blue-800 font-mono">{block.incident_id}</span>
                  </div>
                );
              
              case 'description_box':
                return (
                  <div key={index} className="border-l-4 border-gray-300 pl-4 py-3 bg-gray-50 rounded-r my-4">
                    <div className="font-semibold text-gray-900 mb-2">{block.label}</div>
                    <ul className="space-y-1 text-gray-700">
                      {block.items.map((item, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-gray-400">-</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              
              case 'code':
                return (
                  <div key={index} className="my-4 rounded-md overflow-hidden bg-gray-900">
                    <div className="bg-gray-800 px-4 py-1 text-xs text-gray-400 font-mono">
                      {block.language || 'text'}
                    </div>
                    <pre className="p-4 overflow-x-auto text-sm text-green-400 font-mono">
                      <code>{block.content}</code>
                    </pre>
                  </div>
                );
              
              case 'image':
                return (
                  <figure key={index} className="my-6">
                    <img src={block.data_url} alt={block.caption} className="max-w-full h-auto rounded-md border border-gray-200" />
                    {block.caption && (
                      <figcaption className="text-center text-sm text-gray-500 mt-2">{block.caption}</figcaption>
                    )}
                  </figure>
                );
              
              case 'table':
                return (
                  <div key={index} className="overflow-x-auto my-4">
                    <table className="min-w-full border-collapse border border-gray-300 text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          {block.headers.map((h, i) => (
                            <th key={i} className="border border-gray-300 px-4 py-2 text-left font-semibold text-gray-900">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {block.rows.map((row, i) => (
                          <tr key={i} className="hover:bg-gray-50">
                            {row.map((cell, j) => (
                              <td key={j} className="border border-gray-300 px-4 py-2">{cell}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              
              default:
                return null;
            }
          })}
        </div>
      </div>
    </div>
  );
}