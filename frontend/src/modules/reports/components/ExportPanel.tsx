import React, { useState } from 'react';
import Swal from 'sweetalert2';
import { IncidentReport } from '../../../types';
import { Save, Loader2 } from 'lucide-react';
import { apiFetch } from '../../../api/chat';
import { NTT_BLUE } from '../../../ui/Brand';

interface Props {
  report: IncidentReport;
  editingFilename: string | null;
}

export function ExportPanel({ report, editingFilename }: Props) {
  const [isSaving, setIsSaving] = useState(false);

  const generateMarkdown = () => {
    let md = `# Incident Report: ${report.metadata.title || 'Untitled'}\n\n`;
    
    // Standard Metadata
    md += `**Incident ID:** ${report.metadata.incident_id}\n`;
    md += `**Caller:** ${report.metadata.caller}\n`;
    md += `**Date:** ${report.metadata.date}\n`;
    md += `**Category:** ${report.metadata.category}\n`;
    if (report.metadata.subcategory) {
      md += `**Subcategory:** ${report.metadata.subcategory}\n`;
    }
    
    // Custom Metadata Fields
    const standardFields = ['incident_id', 'title', 'caller', 'category', 'subcategory', 'date'];
    const customFields = Object.keys(report.metadata).filter(key => !standardFields.includes(key));
    if (customFields.length > 0) {
      md += `\n## Custom Fields\n`;
      customFields.forEach(field => {
        md += `**${field}:** ${report.metadata[field]}\n`;
      });
    }
    
    md += `\n---\n\n`;

    // Helper to convert HTML to plain text
    const htmlToPlainText = (html: string): string => {
      const div = document.createElement('div');
      div.innerHTML = html;
      return div.textContent || div.innerText || '';
    };

    // Blocks
    report.blocks.forEach(block => {
      switch (block.type) {
        case 'heading':
          if (block.title) {
            md += `### ${block.title}\n\n`;
          }
          md += `${'#'.repeat(block.level)} ${block.content}\n\n`;
          break;
        case 'paragraph':
          if (block.title) {
            md += `### ${block.title}\n\n`;
          }
          const plainText = htmlToPlainText(block.content);
          md += `${plainText}\n\n`;
          break;
        case 'list':
          if (block.title) {
            md += `### ${block.title}\n\n`;
          }
          const isDescBox = block.label && block.label.trim() !== '';
          if (isDescBox) {
            md += `> **${block.label}**\n`;
            block.items.forEach(item => {
              md += `> - ${item}\n`;
            });
          } else {
            block.items.forEach((item, i) => {
              md += `${block.ordered ? `${i + 1}.` : '-'} ${item}\n`;
            });
          }
          md += '\n';
          break;
        case 'incident_example':
          if (block.title) {
            md += `### ${block.title}\n\n`;
          }
          md += `### Incident example: ${block.incident_id}\n`;
          if (block.link) {
            md += `[View Incident](${block.link})\n`;
          }
          md += '\n';
          break;
        case 'code':
          block.items.forEach((item: any) => {
            if (item.type === 'code') {
              if (item.title) {
                md += `## ${item.title}\n\n`;
              }
              if (item.header) {
                md += `### ${item.header}\n\n`;
              }
              md += `\`\`\`${item.language}\n${item.content}\n\`\`\`\n\n`;
            } else if (item.type === 'description') {
              if (item.title) {
                md += `## ${item.title}\n\n`;
              }
              const plainText = htmlToPlainText(item.content);
              md += `${plainText}\n\n`;
            }
          });
          break;
        case 'image':
          if (block.title) {
            md += `### ${block.title}\n\n`;
          }
          const imgSrc = block.data_url.length > 1000 ? '[Base64 Image Data Omitted for Readability]' : block.data_url;
          md += `![${block.caption}](${imgSrc})\n\n`;
          break;
        case 'table':
          if (block.title) {
            md += `### ${block.title}\n\n`;
          }
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

  const handleSaveReport = async () => {
    setIsSaving(true);
    
    try {
      const markdown = generateMarkdown();
      
      const response = await apiFetch('/api/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          report,
          markdown,
          editingFilename
        }),
      });

      if (response.status === 409) {
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

      if (response.status === 403) {
        await Swal.fire({
          icon: 'error',
          title: 'Not allowed',
          text: 'Your account has read-only access and cannot save reports.',
          confirmButtonColor: '#3b82f6',
        });
        setIsSaving(false);
        return;
      }

      if (response.status === 401) {
        await Swal.fire({
          icon: 'error',
          title: 'Session expired',
          text: 'Please sign in again to save this report.',
          confirmButtonColor: '#3b82f6',
        });
        setIsSaving(false);
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to save report');
      }
      
      const data = await response.json();
      
      const successMessage = data.isUpdating
        ? 'Your report has been successfully updated. Download it now:' 
        : 'Your incident report has been saved. Download it now:';
      
      await Swal.fire({
        icon: 'success',
        title: 'Report Saved Successfully!',
        html: `
          <div style="text-align: left; margin: 20px 0;">
            <p style="margin-bottom: 15px;">${successMessage}</p>
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
    
    } catch (error) {
      console.error('Error saving:', error);
      await Swal.fire({
        icon: 'error',
        title: 'Error',
        text: 'Failed to save report to the server.',
        confirmButtonColor: '#ef4444',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="border-app mt-8 border-t pt-6">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
        <button
          onClick={handleSaveReport}
          disabled={isSaving}
          className="flex items-center rounded-lg px-6 py-3 font-medium text-white transition hover:brightness-110 disabled:opacity-70"
          style={{ background: NTT_BLUE }}
        >
          {isSaving ? (
            <Loader2 className="w-5 h-5 mr-2 animate-spin" />
          ) : (
            <Save className="w-5 h-5 mr-2" />
          )}
          {isSaving ? 'Saving...' : editingFilename ? 'Update Report' : 'Generate & Save Report'}
        </button>
      </div>
    </div>
  );
}
