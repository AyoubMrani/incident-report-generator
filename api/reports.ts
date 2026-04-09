import { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';

const BUCKET_NAME = 'reports';

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

console.log('Supabase URL:', supabaseUrl ? 'Set' : 'NOT SET');
console.log('Supabase Key:', serviceRoleKey ? 'Set' : 'NOT SET');

if (!supabaseUrl || !serviceRoleKey) {
  console.error('Missing Supabase server environment variables!');
}

const supabaseServer = supabaseUrl && serviceRoleKey 
  ? createClient(supabaseUrl, serviceRoleKey)
  : null;

interface ReportData {
  report: {
    metadata: {
      incident_id?: string;
      [key: string]: unknown;
    };
    blocks: Array<any>;
    [key: string]: unknown;
  };
  markdown: string;
}

// Check if incident ID already exists
async function incidentIdExists(incidentId: string): Promise<boolean> {
  if (!supabaseServer) return false;
  
  const folderPath = `incidents/${incidentId}`;
  try {
    const { data, error } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .list(folderPath);
    
    if (error) {
      console.error('Error checking incident ID:', error);
      // If we get an error, assume folder doesn't exist
      return false;
    }
    
    // If data exists and has files, the incident exists
    return data && data.length > 0;
  } catch (err) {
    console.error('Error in incidentIdExists:', err);
    return false;
  }
}

// Extract base64 images from blocks and save them
async function extractAndSaveImages(
  blocks: Array<any>,
  incidentId: string,
  timestamp: number
): Promise<{ updatedBlocks: Array<any>; imageCount: number }> {
  const updatedBlocks = JSON.parse(JSON.stringify(blocks));
  let imageCount = 0;

  for (let i = 0; i < updatedBlocks.length; i++) {
    const block = updatedBlocks[i];
    if (block.type === 'image' && block.data_url && block.data_url.startsWith('data:')) {
      try {
        // Extract base64 data and convert to buffer
        const matches = block.data_url.match(/^data:([a-zA-Z0-9+/]+);base64,(.+)$/);
        if (!matches) continue;

        const mimeType = matches[1];
        const base64Data = matches[2];
        const binaryString = Buffer.from(base64Data, 'base64');

        // Determine file extension
        const ext = mimeType.split('/')[1] || 'jpg';
        const imageName = `image_${block.id || `${timestamp}_${i}`}.${ext}`;
        const imagePath = `incidents/${incidentId}/images/${imageName}`;

        // Upload image
        const { error } = await supabaseServer!.storage
          .from(BUCKET_NAME)
          .upload(imagePath, binaryString, { contentType: mimeType });

        if (error) {
          console.error(`Error uploading image ${imagePath}:`, error);
          continue;
        }

        // Update block with relative path
        block.image_path = `images/${imageName}`;
        delete block.data_url; // Remove base64 data
        imageCount++;
      } catch (err) {
        console.error('Error processing image:', err);
      }
    }
  }

  return { updatedBlocks, imageCount };
}

export default async (req: VercelRequest, res: VercelResponse) => {
  if (!supabaseServer) {
    return res.status(500).json({ error: 'Supabase not configured' });
  }

  // POST - Save report
  if (req.method === 'POST') {
    try {
      console.log('POST /api/reports - Saving report...');
      const { report, markdown } = req.body as ReportData;
      let incidentId = report.metadata.incident_id || `untitled-${Date.now()}`;
      
      const safeIncidentId = incidentId
        .replace(/[^a-z0-9]/gi, '_')
        .toLowerCase();

      // Check if incident ID already exists
      const exists = await incidentIdExists(safeIncidentId);
      if (exists) {
        console.log('Incident ID already exists:', safeIncidentId);
        return res.status(409).json({ 
          error: 'Incident ID already exists',
          duplicate: true,
          incident_id: safeIncidentId
        });
      }

      const timestamp = Date.now();
      const jsonFilename = `incident_${safeIncidentId}_${timestamp}.json`;
      const mdFilename = `incident_${safeIncidentId}_${timestamp}.md`;
      const folderPath = `incidents/${safeIncidentId}`;

      console.log('Processing report with incident ID:', safeIncidentId);

      // Extract and save images, get updated blocks with relative paths
      const { updatedBlocks, imageCount } = await extractAndSaveImages(
        report.blocks,
        safeIncidentId,
        timestamp
      );

      console.log(`Extracted and saved ${imageCount} images`);

      // Create updated report with relative image paths
      const updatedReport = {
        ...report,
        blocks: updatedBlocks,
      };

      // Generate markdown with relative image paths
      let updatedMarkdown = `# Incident Report: ${report.metadata.title || 'Untitled'}\n\n`;
      
      updatedMarkdown += `**Incident ID:** ${report.metadata.incident_id}\n`;
      updatedMarkdown += `**Caller:** ${report.metadata.caller}\n`;
      updatedMarkdown += `**Date:** ${report.metadata.date}\n`;
      updatedMarkdown += `**Category:** ${report.metadata.category}\n`;
      if (report.metadata.subcategory) {
        updatedMarkdown += `**Subcategory:** ${report.metadata.subcategory}\n`;
      }
      updatedMarkdown += `\n---\n\n`;

      updatedBlocks.forEach((block: any) => {
        switch (block.type) {
          case 'heading':
            updatedMarkdown += `${'#'.repeat(block.level)} ${block.content}\n\n`;
            break;
          case 'paragraph':
            updatedMarkdown += `${block.content}\n\n`;
            break;
          case 'list':
            block.items.forEach((item: string, i: number) => {
              updatedMarkdown += `${block.ordered ? `${i + 1}.` : '-'} ${item}\n`;
            });
            updatedMarkdown += '\n';
            break;
          case 'incident_example':
            updatedMarkdown += `### Incident example: ${block.incident_id}\n\n`;
            break;
          case 'description_box':
            updatedMarkdown += `> **${block.label}**\n`;
            block.items.forEach((item: string) => {
              updatedMarkdown += `> - ${item}\n`;
            });
            updatedMarkdown += '\n';
            break;
          case 'code':
            updatedMarkdown += `\`\`\`${block.language}\n${block.content}\n\`\`\`\n\n`;
            break;
          case 'image':
            updatedMarkdown += `![${block.caption || 'Image'}](${block.image_path})\n\n`;
            break;
          case 'table':
            updatedMarkdown += `| ${block.headers.join(' | ')} |\n`;
            updatedMarkdown += `| ${block.headers.map(() => '---').join(' | ')} |\n`;
            block.rows.forEach((row: string[]) => {
              updatedMarkdown += `| ${row.join(' | ')} |\n`;
            });
            updatedMarkdown += '\n';
            break;
        }
      });

      console.log('Uploading to Supabase:', { BUCKET_NAME, folderPath, jsonFilename, mdFilename });

      // Upload JSON file to folder
      const { error: jsonError } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .upload(`${folderPath}/${jsonFilename}`, JSON.stringify(updatedReport, null, 2), {
          contentType: 'application/json',
        });

      if (jsonError) {
        console.error('JSON upload error:', jsonError);
        throw jsonError;
      }

      // Upload Markdown file to folder
      const { error: mdError } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .upload(`${folderPath}/${mdFilename}`, updatedMarkdown, {
          contentType: 'text/markdown',
        });

      if (mdError) {
        console.error('MD upload error:', mdError);
        throw mdError;
      }

      console.log('Upload successful!');
      res.status(200).json({
        success: true,
        jsonUrl: `/api/download?filename=incidents/${safeIncidentId}/${jsonFilename}`,
        mdUrl: `/api/download?filename=incidents/${safeIncidentId}/${mdFilename}`,
        jsonFilename,
        mdFilename,
        incident_id: safeIncidentId,
      });
    } catch (error) {
      console.error('Error saving report:', error);
      res.status(500).json({ error: 'Failed to save report', details: String(error) });
    }
  }

  // GET - List reports
  else if (req.method === 'GET') {
    try {
      const { data: items, error } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .list('incidents');

      if (error) throw error;

      const reports = [];
      
      // Each item in incidents/ is a folder (incident ID)
      for (const item of items) {
        // Folders don't have metadata.mimetype
        if (!item.metadata || !item.metadata.mimetype) {
          const incidentId = item.name;
          try {
            const { data: files, error: listError } = await supabaseServer.storage
              .from(BUCKET_NAME)
              .list(`incidents/${incidentId}`);

            if (listError) throw listError;

            // Find JSON files in the incident folder
            for (const file of files) {
              if (file.name.endsWith('.json')) {
                try {
                  const { data, error: readError } = await supabaseServer.storage
                    .from(BUCKET_NAME)
                    .download(`incidents/${incidentId}/${file.name}`);

                  if (readError) throw readError;

                  const text = await data.text();
                  const parsed = JSON.parse(text);
                  reports.push({
                    filename: `incidents/${incidentId}/${file.name}`,
                    incident_id: incidentId,
                    metadata: parsed.metadata,
                    timestamp: new Date(file.updated_at).getTime(),
                  });
                } catch (err) {
                  console.error(`Error reading report file incidents/${incidentId}/${file.name}:`, err);
                }
              }
            }
          } catch (err) {
            console.error(`Error listing incident ${incidentId}:`, err);
          }
        }
      }

      reports.sort((a, b) => b.timestamp - a.timestamp);

      res.status(200).json({ reports });
    } catch (error) {
      console.error('Error listing reports:', error);
      res.status(500).json({ error: 'Failed to list reports' });
    }
  }

  else {
    res.status(405).json({ error: 'Method not allowed' });
  }
};
