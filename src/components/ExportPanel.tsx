import React, { useState } from 'react';
import { IncidentReport } from '../types';
import { FileJson, FileText, Save, Download, Loader2, CheckCircle2 } from 'lucide-react';

interface Props {
  report: IncidentReport;
}

export function ExportPanel({ report }: Props) {
  const [isSaving, setIsSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{
    jsonUrl: string;
    mdUrl: string;
    jsonFilename: string;
    mdFilename: string;
  } | null>(null);

  const generateMarkdown = () => {
    let md = `# Incident Report: ${report.metadata.title || 'Untitled'}\n\n`;
    
    // Metadata
    md += `**Incident ID:** ${report.metadata.incident_id}\n`;
    md += `**Caller:** ${report.metadata.caller}\n`;
    md += `**Date:** ${report.metadata.date}\n`;
    md += `**Category:** ${report.metadata.category}\n`;
    if (report.metadata.subcategory) {
      md += `**Subcategory:** ${report.metadata.subcategory}\n`;
    }
    md += `\n---\n\n`;

    // Blocks
    report.blocks.forEach(block => {
      switch (block.type) {
        case 'heading':
          md += `${'#'.repeat(block.level)} ${block.content}\n\n`;
          break;
        case 'paragraph':
          md += `${block.content}\n\n`;
          break;
        case 'list':
          block.items.forEach((item, i) => {
            md += `${block.ordered ? `${i + 1}.` : '-'} ${item}\n`;
          });
          md += '\n';
          break;
        case 'incident_example':
          md += `### Incident example: ${block.incident_id}\n\n`;
          break;
        case 'description_box':
          md += `> **${block.label}**\n`;
          block.items.forEach(item => {
            md += `> - ${item}\n`;
          });
          md += '\n';
          break;
        case 'code':
          md += `\`\`\`${block.language}\n${block.content}\n\`\`\`\n\n`;
          break;
        case 'image':
          const imgSrc = block.data_url.length > 1000 ? '[Base64 Image Data Omitted for Readability]' : block.data_url;
          md += `![${block.caption}](${imgSrc})\n\n`;
          break;
        case 'table':
          md += `| ${block.headers.join(' | ')} |\n`;
          md += `| ${block.headers.map(() => '---').join(' | ')} |\n`;
          block.rows.forEach(row => {
            md += `| ${row.join(' | ')} |\n`;
          });
          md += '\n';
          break;
      }
    });

    return md;
  };

  const handleSaveAndExport = async () => {
    setIsSaving(true);
    setSaveResult(null);
    
    try {
      const markdown = generateMarkdown();
      
      const response = await fetch('/api/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          report,
          markdown
        }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to save report');
      }
      
      const data = await response.json();
      setSaveResult(data);
    } catch (error) {
      console.error('Error saving:', error);
      alert('Failed to save report to the server.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mt-8 pt-6 border-t border-gray-200">
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
        <button
          onClick={handleSaveAndExport}
          disabled={isSaving}
          className="flex items-center px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-70"
        >
          {isSaving ? (
            <Loader2 className="w-5 h-5 mr-2 animate-spin" />
          ) : (
            <Save className="w-5 h-5 mr-2" />
          )}
          {isSaving ? 'Saving to Server...' : 'Generate & Save Report'}
        </button>
      </div>

      {saveResult && (
        <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-center text-green-800 font-medium mb-3">
            <CheckCircle2 className="w-5 h-5 mr-2 text-green-600" />
            Report successfully saved to the server!
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <a
              href={saveResult.jsonUrl}
              download={saveResult.jsonFilename}
              className="flex items-center justify-center px-4 py-2 bg-gray-800 text-white rounded hover:bg-gray-700 transition-colors"
            >
              <FileJson className="w-4 h-4 mr-2" />
              Download JSON
            </a>
            <a
              href={saveResult.mdUrl}
              download={saveResult.mdFilename}
              className="flex items-center justify-center px-4 py-2 bg-white text-gray-800 border border-gray-300 rounded hover:bg-gray-50 transition-colors"
            >
              <FileText className="w-4 h-4 mr-2" />
              Download Markdown
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
