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
    // Extract filename from query parameter (now supports paths like "incidents/inc00001/...")
    const filename = req.query.filename as string;

    if (!filename) {
      console.error('No filename provided');
      return res.status(400).json({ error: 'Filename required' });
    }

    // Security: prevent directory traversal attacks (but allow normal paths)
    if (filename.includes('..')) {
      return res.status(400).json({ error: 'Invalid filename' });
    }

    console.log('Reading file:', filename);

    const { data, error } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .download(filename);

    if (error) throw error;

    const content = await data.text();
    const report = JSON.parse(content);

    // Convert image_path back to data_url for display
    const incidentMatch = filename.match(/^incidents\/([^/]+)\//);
    if (incidentMatch && report.blocks) {
      const incidentId = incidentMatch[1];
      
      for (const block of report.blocks) {
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
            console.error('Error converting image_path to data_url:', err);
          }
        }
      }
    }

    res.setHeader('Content-Type', 'application/json');
    res.status(200).send(JSON.stringify(report));
  } catch (error) {
    console.error('Error reading report content:', error);
    res.status(500).json({ error: 'Failed to read report content' });
  }
};

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
