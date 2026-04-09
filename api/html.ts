import { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';

const BUCKET_NAME = 'reports';

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const supabaseServer = supabaseUrl && serviceRoleKey 
  ? createClient(supabaseUrl, serviceRoleKey)
  : null;

export default async (req: VercelRequest, res: VercelResponse) => {
  if (!supabaseServer) {
    return res.status(500).json({ error: 'Supabase not configured' });
  }

  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const filename = req.query.filename as string;

    if (!filename) {
      return res.status(400).json({ error: 'Filename required' });
    }

    // Security: prevent directory traversal
    if (filename.includes('..')) {
      return res.status(400).json({ error: 'Invalid filename' });
    }

    console.log('Generating HTML for:', filename);

    const { data, error } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .download(filename);

    if (error) throw error;

    const content = await data.text();
    const report = JSON.parse(content);
    const metadata = report.metadata || {};
    const blocks = report.blocks || [];

    // Extract incident_id from filename like "incidents/inc00001/incident_inc00001_timestamp.json"
    const incidentMatch = filename.match(/^incidents\/([^/]+)\//);
    const incidentId = incidentMatch ? incidentMatch[1] : 'unknown';

    // Convert image_path to base64 for embedded HTML
    for (const block of blocks) {
      if (block.type === 'image' && block.image_path && !block.data_url) {
        try {
          const imagePath = `incidents/${incidentId}/${block.image_path}`;
          const { data: imageData, error: imageError } = await supabaseServer.storage
            .from(BUCKET_NAME)
            .download(imagePath);

          if (!imageError) {
            const buffer = await imageData.arrayBuffer();
            const base64 = Buffer.from(buffer).toString('base64');
            const ext = block.image_path.split('.').pop() || 'jpg';
            const mimeType = getMimeType(ext);
            block.data_url = `data:${mimeType};base64,${base64}`;
          }
        } catch (err) {
          console.error('Error converting image_path to base64:', err);
        }
      }
    }

    // Build HTML
    let html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(metadata.title || 'Incident Report')}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; line-height: 1.6; color: #333; }
    .container { max-width: 900px; margin: 0 auto; padding: 40px 20px; }
    .header { border-bottom: 2px solid #e5e7eb; padding-bottom: 30px; margin-bottom: 30px; }
    .incident-badge { display: inline-block; background-color: #dbeafe; color: #1e40af; padding: 8px 12px; border-radius: 6px; font-family: monospace; font-size: 14px; margin-bottom: 10px; }
    h1 { font-size: 32px; font-weight: bold; margin: 15px 0; }
    .metadata { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 30px; font-size: 14px; }
    .metadata-item { }
    .metadata-label { color: #6b7280; margin-bottom: 5px; }
    .metadata-value { font-weight: 500; color: #111; }
    .content { margin-top: 30px; }
    h2 { font-size: 24px; margin: 20px 0 15px 0; }
    h3 { font-size: 20px; margin: 16px 0 12px 0; }
    h4 { font-size: 16px; margin: 12px 0 8px 0; }
    p { margin-bottom: 12px; }
    ul, ol { margin-left: 20px; margin-bottom: 12px; }
    li { margin-bottom: 6px; }
    img { max-width: 100%; height: auto; border-radius: 6px; border: 1px solid #e5e7eb; margin: 20px 0; display: block; }
    figcaption { text-align: center; font-size: 14px; color: #6b7280; margin-top: 8px; }
    .description-box { border-left: 4px solid #d1d5db; padding-left: 16px; padding: 12px 16px; background-color: #f9fafb; border-radius: 4px; margin: 15px 0; }
    .description-box-title { font-weight: 600; color: #111; margin-bottom: 8px; }
    .incident-example { background-color: #eff6ff; padding: 16px; border-radius: 6px; border: 1px solid #bfdbfe; margin: 15px 0; }
    .incident-example-title { font-weight: 600; color: #1e40af; }
    .incident-example-id { font-family: monospace; color: #1e3a8a; }
    pre { background-color: #111; color: #22c55e; padding: 16px; border-radius: 6px; overflow-x: auto; margin: 15px 0; }
    code { font-family: 'Courier New', monospace; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    th { background-color: #f3f4f6; font-weight: 600; border: 1px solid #d1d5db; padding: 12px; text-align: left; }
    td { border: 1px solid #d1d5db; padding: 12px; }
    tr:hover { background-color: #f9fafb; }
    @media print {
      body { margin: 0; }
      .container { max-width: 100%; }
      img { max-width: 100%; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="incident-badge">${escapeHtml(metadata.incident_id || 'No ID')}</div>
      <h1>${escapeHtml(metadata.title || 'Untitled Report')}</h1>
      <div class="metadata">
        ${metadata.date ? `<div class="metadata-item"><div class="metadata-label">Date</div><div class="metadata-value">${escapeHtml(metadata.date)}</div></div>` : ''}
        ${metadata.caller ? `<div class="metadata-item"><div class="metadata-label">Caller</div><div class="metadata-value">${escapeHtml(metadata.caller)}</div></div>` : ''}
        ${metadata.category ? `<div class="metadata-item"><div class="metadata-label">Category</div><div class="metadata-value">${escapeHtml(metadata.category)}</div></div>` : ''}
        ${metadata.subcategory ? `<div class="metadata-item"><div class="metadata-label">Subcategory</div><div class="metadata-value">${escapeHtml(metadata.subcategory)}</div></div>` : ''}
      </div>
    </div>
    
    <div class="content">
      ${blocks.map((block: any) => {
        switch (block.type) {
          case 'heading':
            const tag = `h${block.level}`;
            return `<${tag}>${escapeHtml(block.content)}</${tag}>`;
          
          case 'paragraph':
            return `<p>${escapeHtml(block.content)}</p>`;
          
          case 'list':
            const listTag = block.ordered ? 'ol' : 'ul';
            const items = block.items.map((item: string) => `<li>${escapeHtml(item)}</li>`).join('');
            return `<${listTag}>${items}</${listTag}>`;
          
          case 'incident_example':
            return `<div class="incident-example"><span class="incident-example-title">Incident example:</span> <span class="incident-example-id">${escapeHtml(block.incident_id)}</span></div>`;
          
          case 'description_box':
            const desc_items = block.items.map((item: string) => `<div>- ${escapeHtml(item)}</div>`).join('');
            return `<div class="description-box"><div class="description-box-title">${escapeHtml(block.label)}</div>${desc_items}</div>`;
          
          case 'code':
            return `<pre><code>${escapeHtml(block.content)}</code></pre>`;
          
          case 'image':
            return `<figure>
              <img src="${block.data_url}" alt="${escapeHtml(block.caption || 'Image')}" />
              ${block.caption ? `<figcaption>${escapeHtml(block.caption)}</figcaption>` : ''}
            </figure>`;
          
          case 'table':
            const headers = block.headers.map((h: string) => `<th>${escapeHtml(h)}</th>`).join('');
            const rows = block.rows.map((row: string[]) => 
              `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`
            ).join('');
            return `<table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
          
          default:
            return '';
        }
      }).join('\n')}
    </div>
  </div>
</body>
</html>`;

    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    const downloadName = filename.split('/').pop()?.replace('.json', '.html') || 'report.html';
    res.setHeader('Content-Disposition', `attachment; filename="${downloadName}"`);
    res.status(200).send(html);
  } catch (error) {
    console.error('Error generating HTML:', error);
    res.status(500).json({ error: 'Failed to generate HTML' });
  }
};

function escapeHtml(text: string): string {
  const map: { [key: string]: string } = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}

function getMimeType(ext: string): string {
  const mimeTypes: { [key: string]: string } = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    webp: 'image/webp',
  };
  return mimeTypes[ext.toLowerCase()] || 'image/jpeg';
}
