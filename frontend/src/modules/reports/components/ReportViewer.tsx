import React, { useEffect, useState } from 'react';
import { IncidentReport } from '../../../types';
import { Loader2, ArrowLeft, Download, FileJson, FileText, Trash2, Edit, AlertTriangle } from 'lucide-react';
import Swal from 'sweetalert2';
import { apiFetch } from '../../../api/chat';
import { NTT_BLUE } from '../../../ui/Brand';

interface Props {
  filename: string;
  onBack: () => void;
  onEdit: (filename: string) => void;
}

export function ReportViewer({ filename, onBack, onEdit }: Props) {
  const [report, setReport] = useState<IncidentReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDeleteReport = async () => {
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

    setIsDeleting(true);
    try {
      const response = await apiFetch(`/api/delete?incident_id=${encodeURIComponent(incident_id)}`, {
        method: 'DELETE',
      });
      if (response.status === 403) {
        await Swal.fire({ title: 'Not allowed', text: 'Your account has read-only access.', icon: 'error' });
        setIsDeleting(false);
        return;
      }
      if (!response.ok) throw new Error('Failed to delete report');

      await Swal.fire({ title: 'Deleted!', text: 'Report has been deleted.', icon: 'success', timer: 1500 });
      onBack();
    } catch (err) {
      setError('Could not delete report.');
      console.error(err);
      await Swal.fire({ title: 'Error!', text: 'Failed to delete report.', icon: 'error' });
      setIsDeleting(false);
    }
  };

  useEffect(() => {
    const fetchReport = async () => {
      setError(null);
      try {
        const response = await apiFetch(`/api/reports/content/${encodeURIComponent(filename)}`);
        // Same rule as the list: name the real cause instead of a generic one.
        if (response.status === 401) {
          setError('Your session has expired. Sign in again to view this report.');
          return;
        }
        if (response.status === 403) {
          setError('Your account does not have permission to view this report.');
          return;
        }
        if (response.status === 404) {
          setError('This report no longer exists. It may have been deleted.');
          return;
        }
        if (!response.ok) throw new Error(`Request failed (${response.status})`);
        const data = await response.json();
        setReport(data);
      } catch (err) {
        setError('Could not load this report. Check your connection and try again.');
        console.error(err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchReport();
  }, [filename]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-6 h-6 animate-spin" style={{ color: NTT_BLUE }} />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-5 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
        <AlertTriangle className="mt-0.5 w-5 h-5 shrink-0" />
        <div>
          <p className="text-sm">{error || 'Report not found'}</p>
          <button onClick={onBack} className="mt-2 text-sm font-medium underline underline-offset-2">
            ← Back to list
          </button>
        </div>
      </div>
    );
  }

  const metadata = report?.metadata || {};
  const blocks = report?.blocks || [];
  const mdFilename = filename.replace('.json', '.md');

  return (
    <div className="bg-app-elevated border-app overflow-hidden rounded-xl border shadow-sm">
      <div className="bg-app-surface border-app flex flex-col items-start justify-between gap-4 border-b p-4 sm:flex-row sm:items-center">
        <button onClick={onBack} className="text-app-muted hover:text-app flex items-center text-sm transition">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back to List
        </button>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => onEdit(filename)}
            className="flex items-center rounded-lg px-3 py-1.5 text-[13px] font-medium transition"
            style={{ background: `${NTT_BLUE}14`, color: NTT_BLUE }}
            title="Edit this report"
          >
            <Edit className="mr-1.5 h-4 w-4" />
            Edit
          </button>
          <a
            href={`/api/download?filename=${encodeURIComponent(filename)}`}
            download
            className="bg-app-hover text-app-muted hover:text-app flex items-center rounded-lg px-3 py-1.5 text-[13px] transition"
          >
            <FileJson className="mr-1.5 h-4 w-4" />
            JSON
          </a>
          <a
            href={`/api/download?filename=${encodeURIComponent(mdFilename)}`}
            download
            className="bg-app-hover text-app-muted hover:text-app flex items-center rounded-lg px-3 py-1.5 text-[13px] transition"
          >
            <FileText className="mr-1.5 h-4 w-4" />
            Markdown
          </a>
          <a
            href={`/api/html?filename=${encodeURIComponent(filename)}`}
            download
            className="flex items-center rounded-lg bg-emerald-50 px-3 py-1.5 text-[13px] text-emerald-700 transition hover:bg-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:hover:bg-emerald-950/50"
            title="Download as HTML with embedded images"
          >
            <Download className="mr-1.5 h-4 w-4" />
            HTML
          </a>
          <button
            onClick={handleDeleteReport}
            disabled={isDeleting}
            className="flex items-center rounded-lg bg-red-50 px-3 py-1.5 text-[13px] text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-red-950/30 dark:text-red-400 dark:hover:bg-red-950/50"
            title="Delete this report"
          >
            {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <div className="p-6 sm:p-8">
        {/* Metadata header */}
        <div className="border-app mb-8 border-b pb-6">
          <div className="mb-2 flex items-center gap-3">
            <span
              className="rounded-md px-2.5 py-1 font-mono text-sm"
              style={{ background: `${NTT_BLUE}14`, color: NTT_BLUE }}
            >
              {metadata.incident_id || 'No ID'}
            </span>
            <span className="text-app-muted text-sm">{metadata.date}</span>
          </div>
          <h1 className="text-app mb-4 text-2xl font-semibold tracking-tight sm:text-3xl">
            {metadata.title || 'Untitled Report'}
          </h1>

          <div className="grid grid-cols-2 gap-x-8 gap-y-4 text-sm sm:grid-cols-3">
            <div>
              <span className="text-app-muted mb-1 block">Caller</span>
              <span className="text-app font-medium">{metadata.caller || '-'}</span>
            </div>
            <div>
              <span className="text-app-muted mb-1 block">Category</span>
              <span className="text-app font-medium">{metadata.category || '-'}</span>
            </div>
            <div>
              <span className="text-app-muted mb-1 block">Subcategory</span>
              <span className="text-app font-medium">{metadata.subcategory || '-'}</span>
            </div>
          </div>

          {(() => {
            const standardFields = ['incident_id', 'title', 'caller', 'category', 'subcategory', 'date'];
            const customFields = Object.keys(metadata).filter((key) => !standardFields.includes(key));
            return customFields.length > 0 ? (
              <div className="border-app mt-6 border-t pt-6">
                <h3 className="text-app mb-3 text-sm font-semibold">Custom Fields</h3>
                <div className="grid grid-cols-2 gap-x-8 gap-y-4 text-sm sm:grid-cols-3">
                  {customFields.map((field) => (
                    <div key={field}>
                      <span className="text-app-muted mb-1 block capitalize">{field}</span>
                      <span className="text-app font-medium">{metadata[field] || '-'}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null;
          })()}
        </div>

        {/* Content blocks — same rendering logic, retheme only. */}
        <div className="text-app space-y-6">
          {blocks.map((block, index) => {
            switch (block.type) {
              case 'heading': {
                const sizeClass =
                  block.level === 1 ? 'text-2xl mt-8 mb-4' :
                  block.level === 2 ? 'text-xl mt-6 mb-3' :
                  block.level === 3 ? 'text-lg mt-4 mb-2' : 'text-base mt-4 mb-2';
                const className = `text-app font-semibold ${sizeClass}`;
                const headingElement =
                  block.level === 1 ? <h1 className={className}>{block.content}</h1> :
                  block.level === 2 ? <h2 className={className}>{block.content}</h2> :
                  block.level === 3 ? <h3 className={className}>{block.content}</h3> :
                  <h4 className={className}>{block.content}</h4>;
                return (
                  <div key={index}>
                    {block.title && <div className="text-app-muted mb-1 text-sm font-semibold uppercase">{block.title}</div>}
                    {headingElement}
                  </div>
                );
              }

              case 'paragraph':
                return (
                  <div key={index}>
                    {block.title && <div className="text-app-muted mb-2 text-sm font-semibold uppercase">{block.title}</div>}
                    <div
                      className="prose prose-sm dark:prose-invert max-w-none"
                      dangerouslySetInnerHTML={{ __html: block.content || '' }}
                    />
                  </div>
                );

              case 'list': {
                const isDescBox = block.label && block.label.trim() !== '';
                if (isDescBox) {
                  return (
                    <div key={index}>
                      {block.title && <div className="text-app-muted mb-2 text-sm font-semibold uppercase">{block.title}</div>}
                      <div className="border-app-strong bg-app-surface my-4 rounded-r border-l-4 py-3 pl-4">
                        <div className="text-app mb-2 font-semibold">{block.label}</div>
                        <ul className="text-app space-y-1">
                          {block.items.map((item, i) => (
                            <li key={i} className="flex gap-2">
                              <span className="text-app-muted">-</span>
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  );
                }
                const ListTag = block.ordered ? 'ol' : 'ul';
                const listClass = block.ordered ? 'list-decimal' : 'list-disc';
                return (
                  <div key={index}>
                    {block.title && <div className="text-app-muted mb-2 text-sm font-semibold uppercase">{block.title}</div>}
                    <ListTag className={`${listClass} space-y-1 pl-5`}>
                      {block.items.map((item, i) => <li key={i}>{item}</li>)}
                    </ListTag>
                  </div>
                );
              }

              case 'incident_example':
                return (
                  <div key={index}>
                    {block.title && <div className="text-app-muted mb-2 text-sm font-semibold uppercase">{block.title}</div>}
                    <div
                      className="my-4 rounded-md border p-4"
                      style={{ background: `${NTT_BLUE}0d`, borderColor: `${NTT_BLUE}33` }}
                    >
                      <div className="mb-2 flex items-center gap-2">
                        <span className="text-app font-semibold">Incident ID:</span>
                        <span className="font-mono" style={{ color: NTT_BLUE }}>{block.incident_id}</span>
                      </div>
                      {block.link && (
                        <div className="flex items-center gap-2">
                          <span className="text-app font-semibold">Link:</span>
                          <a
                            href={block.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="break-all hover:underline"
                            style={{ color: NTT_BLUE }}
                          >
                            {block.link}
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                );

              case 'code':
                return (
                  <div key={index} className="my-4 space-y-4">
                    {block.items.map((item) => (
                      <div key={item.id} className={item.type === 'code' ? 'overflow-hidden rounded-md border border-slate-800 bg-slate-900' : ''}>
                        {item.type === 'code' ? (
                          <>
                            {item.title && (
                              <div className="border-b px-4 py-2" style={{ background: NTT_BLUE, borderColor: NTT_BLUE }}>
                                <h4 className="font-semibold text-white">{item.title}</h4>
                              </div>
                            )}
                            {item.header && (
                              <div className="border-b border-slate-700 bg-slate-800 px-4 py-2">
                                <h4 className="font-semibold text-white">{item.header}</h4>
                              </div>
                            )}
                            <div>
                              <div className="border-b border-slate-700 bg-slate-800 px-4 py-1 font-mono text-xs text-slate-400">
                                {item.language || 'text'}
                              </div>
                              <pre className="overflow-x-auto p-4 font-mono text-sm text-emerald-400">
                                <code>{item.content}</code>
                              </pre>
                            </div>
                          </>
                        ) : (
                          <div className="space-y-2">
                            {item.title && (
                              <div className="bg-violet-600 px-4 py-2">
                                <h4 className="font-semibold text-white">{item.title}</h4>
                              </div>
                            )}
                            <div className="prose prose-sm dark:prose-invert text-app max-w-none px-4 py-4">
                              <div dangerouslySetInnerHTML={{ __html: item.content || '' }} />
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );

              case 'image':
                return (
                  <figure key={index} className="my-6">
                    {block.title && <div className="text-app-muted mb-2 text-sm font-semibold uppercase">{block.title}</div>}
                    <img src={block.data_url} alt={block.caption} className="border-app h-auto max-w-full rounded-md border" />
                    {block.caption && (
                      <figcaption className="text-app-muted mt-2 text-center text-sm">{block.caption}</figcaption>
                    )}
                  </figure>
                );

              case 'table':
                return (
                  <div key={index} className="my-4">
                    {block.title && <div className="text-app-muted mb-2 text-sm font-semibold uppercase">{block.title}</div>}
                    <div className="overflow-x-auto">
                      <table className="border-app min-w-full border-collapse border text-sm">
                        <thead className="bg-app-surface">
                          <tr>
                            {block.headers.map((h, i) => (
                              <th key={i} className="border-app text-app border px-4 py-2 text-left font-semibold">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {block.rows.map((row, i) => (
                            <tr key={i} className="hover:bg-app-hover">
                              {row.map((cell, j) => (
                                <td key={j} className="border-app text-app border px-4 py-2">{cell}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
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
