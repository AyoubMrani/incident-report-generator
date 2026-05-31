import express from 'express';
import { createServer as createViteServer } from 'vite';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = 3000;

  // Increase payload limit for base64 images
  app.use(express.json({ limit: '50mb' }));

  const reportsDir = path.join(process.cwd(), 'reports');
  
  // Ensure reports directory exists
  try {
    await fs.access(reportsDir);
  } catch {
    await fs.mkdir(reportsDir, { recursive: true });
  }

  // API to save report
  app.post('/api/reports', async (req, res) => {
    try {
      const { report, markdown } = req.body;
      const incidentId = report.metadata.incident_id || `untitled-${Date.now()}`;
      const timestamp = Date.now();
      
      // Sanitize incident ID for filename
      const safeIncidentId = incidentId.replace(/[^a-z0-9]/gi, '_').toLowerCase();
      
      const jsonFilename = `incident_${safeIncidentId}_${timestamp}.json`;
      const mdFilename = `incident_${safeIncidentId}_${timestamp}.md`;
      
      await fs.writeFile(path.join(reportsDir, jsonFilename), JSON.stringify(report, null, 2));
      await fs.writeFile(path.join(reportsDir, mdFilename), markdown);
      
      res.json({
        success: true,
        jsonUrl: `/api/reports/download/${jsonFilename}`,
        mdUrl: `/api/reports/download/${mdFilename}`,
        jsonFilename,
        mdFilename
      });
    } catch (error) {
      console.error('Error saving report:', error);
      res.status(500).json({ error: 'Failed to save report' });
    }
  });

  // API to download report
  app.get('/api/reports/download/:filename', (req, res) => {
    const filename = req.params.filename;
    const filepath = path.join(reportsDir, filename);
    res.download(filepath);
  });

  // API to download report (query parameter version)
  app.get('/api/download', (req, res) => {
    const filename = req.query.filename as string;
    if (!filename) {
      return res.status(400).json({ error: 'Filename is required' });
    }
    const filepath = path.join(reportsDir, filename);
    res.download(filepath);
  });

  // API to generate HTML report
  app.get('/api/html', async (req, res) => {
    try {
      // Helper to escape HTML special characters
      const escapeHtml = (text: string): string => {
        const map: { [key: string]: string } = {
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#039;'
        };
        return String(text).replace(/[&<>"']/g, m => map[m]);
      };

      const filename = req.query.filename as string;
      if (!filename) {
        return res.status(400).json({ error: 'Filename is required' });
      }

      const content = await fs.readFile(path.join(reportsDir, filename), 'utf-8');
      const report = JSON.parse(content);
      const metadata = report.metadata || {};

      // Extract custom metadata fields (non-standard fields)
      const standardFields = ['incident_id', 'title', 'caller', 'category', 'subcategory', 'date'];
      const customMetadataItems: string[] = [];
      for (const [key, value] of Object.entries(metadata)) {
        if (!standardFields.includes(key) && value) {
          customMetadataItems.push(`<div class="metadata-item"><span class="metadata-label">${escapeHtml(key)}:</span> ${escapeHtml(String(value))}</div>`);
        }
      }
      const customMetadataHTML = customMetadataItems.length > 0 ? `<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">Custom Fields</h3>${customMetadataItems.join('')}` : '';

      // Build HTML
      let html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${metadata.title || 'Incident Report'}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; color: #333; }
    h1 { color: #1f2937; border-bottom: 3px solid #3b82f6; padding-bottom: 10px; }
    h2 { color: #374151; margin-top: 30px; }
    h3 { color: #6b7280; }
    .metadata { background: #f3f4f6; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    .metadata-item { margin: 8px 0; }
    .metadata-label { font-weight: bold; color: #1f2937; }
    img { max-width: 100%; height: auto; margin: 15px 0; border: 1px solid #d1d5db; border-radius: 5px; }
    code { background: #f3f4f6; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
    pre { background: #1f2937; color: #e5e7eb; padding: 15px; border-radius: 5px; overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; margin: 15px 0; }
    th, td { border: 1px solid #d1d5db; padding: 12px; text-align: left; }
    th { background: #f3f4f6; font-weight: bold; }
    blockquote { border-left: 4px solid #3b82f6; padding-left: 15px; margin-left: 0; color: #6b7280; }
    ul, ol { margin: 10px 0; }
    .page-break { page-break-after: always; margin: 30px 0; }
  </style>
</head>
<body>
  <h1>${metadata.title || 'Incident Report'}</h1>
  
  <div class="metadata">
    <div class="metadata-item"><span class="metadata-label">Incident ID:</span> ${metadata.incident_id || 'N/A'}</div>
    <div class="metadata-item"><span class="metadata-label">Caller:</span> ${metadata.caller || 'N/A'}</div>
    <div class="metadata-item"><span class="metadata-label">Date:</span> ${metadata.date || 'N/A'}</div>
    <div class="metadata-item"><span class="metadata-label">Category:</span> ${metadata.category || 'N/A'}</div>
    ${metadata.subcategory ? `<div class="metadata-item"><span class="metadata-label">Subcategory:</span> ${metadata.subcategory}</div>` : ''}
    ${customMetadataHTML}
  </div>

  <hr />
`;

      // Render blocks
      const blocks = report.blocks || [];
      for (const block of blocks) {
        switch (block.type) {
          case 'heading':
            if (block.title) {
              html += `<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">${escapeHtml(block.title)}</h3>`;
            }
            html += `<h${block.level || 2}>${block.content || ''}</h${block.level || 2}>`;
            break;
          case 'paragraph':
            if (block.title) {
              html += `<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">${escapeHtml(block.title)}</h3>`;
            }
            // Quill stores content as HTML, so we can use it directly
            html += `<div class="paragraph-content">${block.content || '<p></p>'}</div>`;
            break;
          case 'image':
            if (block.title) {
              html += `<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">${escapeHtml(block.title)}</h3>`;
            }
            if (block.data_url) {
              html += `<img src="${block.data_url}" alt="${block.caption || 'Image'}" />`;
            }
            break;
          case 'code':
            (block.items || []).forEach((item: any) => {
              if (item.type === 'code') {
                let codeHtml = `<div style="background: #111827; padding: 1rem; border-radius: 0.375rem; margin: 1rem 0; border: 1px solid #374151; overflow-x: auto;">`;
                if (item.title) {
                  codeHtml += `<h2 style="background: #2563eb; color: white; padding: 0.5rem; margin: -1rem -1rem 0.5rem -1rem; border-radius: 0.375rem 0.375rem 0 0; font-size: 0.875rem;">${escapeHtml(item.title)}</h2>`;
                }
                if (item.header) {
                  codeHtml += `<h3 style="color: white; margin: 0 0 0.5rem 0; font-size: 1rem;">${escapeHtml(item.header)}</h3>`;
                }
                codeHtml += `<div style="font-size: 0.75rem; color: #9ca3af; margin-bottom: 0.5rem;">Language: ${escapeHtml(item.language || 'text')}</div>`;
                codeHtml += `<pre style="margin: 0;"><code style="color: #4ade80; font-family: monospace; font-size: 0.875rem;">${(item.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>`;
                codeHtml += `</div>`;
                html += codeHtml;
              } else if (item.type === 'description') {
                let descHtml = `<div style="margin: 1rem 0; border: 1px solid #e5e7eb; border-radius: 0.375rem; overflow: hidden;">`;
                if (item.title) {
                  descHtml += `<h2 style="background: #a855f7; color: white; padding: 0.5rem; margin: 0; font-size: 0.875rem;">${escapeHtml(item.title)}</h2>`;
                }
                descHtml += `<div style="padding: 1rem; color: #1f2937;">${item.content || ''}</div>`;
                descHtml += `</div>`;
                html += descHtml;
              }
            });
            break;
          case 'table':
            if (block.title) {
              html += `<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">${escapeHtml(block.title)}</h3>`;
            }
            html += `<table><thead><tr>${(block.headers || []).map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>`;
            for (const row of (block.rows || [])) {
              html += `<tr>${row.map((cell: string) => `<td>${cell}</td>`).join('')}</tr>`;
            }
            html += `</tbody></table>`;
            break;
          case 'list':
            if (block.title) {
              html += `<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">${escapeHtml(block.title)}</h3>`;
            }
            const isDescBox = block.label && block.label.trim() !== '';
            if (isDescBox) {
              html += `<blockquote><strong>${block.label || ''}</strong><ul>${(block.items || []).map((item: string) => `<li>${item}</li>`).join('')}</ul></blockquote>`;
            } else {
              const tag = block.ordered ? 'ol' : 'ul';
              html += `<${tag}>${(block.items || []).map((item: string) => `<li>${item}</li>`).join('')}</${tag}>`;
            }
            break;
          case 'incident_example':
            if (block.title) {
              html += `<h3 style="color: #374151; margin-top: 20px; margin-bottom: 10px;">${escapeHtml(block.title)}</h3>`;
            }
            html += `<div class="incident-example" style="background: #eff6ff; padding: 1rem; border-radius: 0.375rem; border: 1px solid #bfdbfe; margin: 1rem 0;">`;
            html += `<h3 style="margin: 0 0 0.5rem 0; color: #1e40af;">Incident example: ${block.incident_id || ''}</h3>`;
            if (block.link) {
              html += `<p style="margin: 0;"><a href="${block.link}" style="color: #2563eb; text-decoration: underline;" target="_blank" rel="noopener noreferrer">${block.link}</a></p>`;
            }
            html += `</div>`;
            break;
        }
      }

      html += `</body></html>`;

      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.setHeader('Content-Disposition', `attachment; filename="report-${metadata.incident_id || 'export'}.html"`);
      res.send(html);
    } catch (error) {
      console.error('Error generating HTML:', error);
      res.status(500).json({ error: 'Failed to generate HTML' });
    }
  });

  // API to list saved reports
  app.get('/api/reports', async (req, res) => {
    try {
      const files = await fs.readdir(reportsDir);
      const jsonFiles = files.filter(f => f.endsWith('.json'));
      
      const reports = [];
      for (const file of jsonFiles) {
        try {
          const content = await fs.readFile(path.join(reportsDir, file), 'utf-8');
          const parsed = JSON.parse(content);
          const stats = await fs.stat(path.join(reportsDir, file));
          reports.push({
            filename: file,
            metadata: parsed.metadata,
            timestamp: stats.mtimeMs
          });
        } catch (err) {
          console.error(`Error reading report file ${file}:`, err);
        }
      }
      
      // Sort by newest first
      reports.sort((a, b) => b.timestamp - a.timestamp);
      res.json({ reports });
    } catch (error) {
      console.error('Error listing reports:', error);
      res.status(500).json({ error: 'Failed to list reports' });
    }
  });

  // API to get specific report content
  app.get('/api/reports/content/:filename', async (req, res) => {
    try {
      const filename = req.params.filename;
      const content = await fs.readFile(path.join(reportsDir, filename), 'utf-8');
      res.json(JSON.parse(content));
    } catch (error) {
      console.error('Error reading report content:', error);
      res.status(500).json({ error: 'Failed to read report content' });
    }
  });

  // API to delete report
  app.delete('/api/delete/:filename?', async (req, res) => {
    try {
      let filename = req.params.filename;
      const incidentId = req.query.incident_id as string;

      // If incident_id is provided, find the latest file for that incident
      if (incidentId && !filename) {
        const files = await fs.readdir(reportsDir);
        const incidentFiles = files.filter(f => f.includes(`incident_${incidentId}_`) && f.endsWith('.json'));
        if (incidentFiles.length === 0) {
          return res.status(404).json({ error: 'Report not found' });
        }
        // Get the latest file for this incident
        filename = incidentFiles[incidentFiles.length - 1];
      }

      if (!filename) {
        return res.status(400).json({ error: 'Filename or incident_id is required' });
      }

      // Security: prevent directory traversal
      if (filename.includes('..') || filename.includes('/')) {
        return res.status(400).json({ error: 'Invalid filename' });
      }

      // Delete both JSON and MD files
      const jsonPath = path.join(reportsDir, filename);
      const mdPath = path.join(reportsDir, filename.replace('.json', '.md'));

      try {
        await fs.unlink(jsonPath);
      } catch (err) {
        console.error(`Error deleting JSON file ${filename}:`, err);
      }

      try {
        await fs.unlink(mdPath);
      } catch (err) {
        console.error(`Error deleting MD file ${filename.replace('.json', '.md')}:`, err);
      }

      res.json({
        success: true,
        message: 'Report deleted successfully',
      });
    } catch (error) {
      console.error('Error deleting report:', error);
      res.status(500).json({ error: 'Failed to delete report' });
    }
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
