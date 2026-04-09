import React, { useState } from 'react';
import Swal from 'sweetalert2';
import { IncidentReport } from '../types';
import { Save, Loader2 } from 'lucide-react';

interface Props {
  report: IncidentReport;
}

export function ExportPanel({ report }: Props) {
  const [isSaving, setIsSaving] = useState(false);

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
      
      if (response.status === 409) {
        // Duplicate incident ID
        const data = await response.json();
        await Swal.fire({
          icon: 'error',
          title: 'Incident ID Already Exists',
          text: `An incident report with ID "${data.incident_id}" already exists. Please change the incident ID and try again.`,
          confirmButtonColor: '#3b82f6',
        });
        setIsSaving(false);
        return;
      }
      
      if (!response.ok) {
        throw new Error('Failed to save report');
      }
      
      const data = await response.json();
      
      // Show success alert with download options
      await Swal.fire({
        icon: 'success',
        title: 'Report Saved Successfully!',
        html: `
          <div style="text-align: left; margin: 20px 0;">
            <p style="margin-bottom: 15px;">Your incident report has been saved. Download it now:</p>
            <div style="display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
              <a href="${data.jsonUrl}" download="${data.jsonFilename}" 
                 style="padding: 10px 16px; background-color: #1f2937; color: white; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;">
                📄 JSON
              </a>
              <a href="${data.mdUrl}" download="${data.mdFilename}"
                 style="padding: 10px 16px; background-color: #1f2937; color: white; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;">
                📝 Markdown
              </a>
            </div>
          </div>
        `,
        confirmButtonText: 'Done',
        confirmButtonColor: '#3b82f6',
        allowOutsideClick: false,
        allowEscapeKey: false,
      });
      
      // Reset the form after confirmation
      setSaveResult(null);
    
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
    </div>
  );
}
