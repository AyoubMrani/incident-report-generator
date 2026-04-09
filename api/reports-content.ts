import { VercelRequest, VercelResponse } from '@vercel/node';
import { supabaseServer } from './supabaseClient.js';

const BUCKET_NAME = 'reports';

export default async (req: VercelRequest, res: VercelResponse) => {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // Extract filename from query parameter
    const filename = req.query.filename as string;

    if (!filename) {
      console.error('No filename provided');
      return res.status(400).json({ error: 'Filename required' });
    }

    // Security: prevent directory traversal
    if (filename.includes('..') || filename.includes('/')) {
      return res.status(400).json({ error: 'Invalid filename' });
    }

    console.log('Reading file:', filename);

    const { data, error } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .download(filename);

    if (error) throw error;

    const content = await data.text();

    res.setHeader('Content-Type', 'application/json');
    res.status(200).send(content);
  } catch (error) {
    console.error('Error reading report content:', error);
    res.status(500).json({ error: 'Failed to read report content' });
  }
};
