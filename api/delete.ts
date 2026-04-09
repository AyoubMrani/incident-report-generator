import { VercelRequest, VercelResponse } from '@vercel/node';
import { supabaseServer } from './supabaseClient.js';

const BUCKET_NAME = 'reports';

export default async (req: VercelRequest, res: VercelResponse) => {
  if (req.method !== 'DELETE') {
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

    // Determine corresponding files
    const mdFilename = filename.replace('.json', '.md');

    console.log('Deleting files:', { filename, mdFilename });

    let deletedJson = false;
    let deletedMd = false;

    // Delete JSON file
    const { error: jsonError } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .remove([filename]);

    if (!jsonError) {
      deletedJson = true;
      console.log('Deleted JSON:', filename);
    } else {
      console.error(`Error deleting JSON file ${filename}:`, jsonError);
    }

    // Delete MD file
    const { error: mdError } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .remove([mdFilename]);

    if (!mdError) {
      deletedMd = true;
      console.log('Deleted MD:', mdFilename);
    } else {
      console.error(`Error deleting MD file ${mdFilename}:`, mdError);
    }

    if (!deletedJson && !deletedMd) {
      return res.status(404).json({ error: 'Files not found' });
    }

    res.status(200).json({
      success: true,
      message: 'Report deleted successfully',
      deletedJson,
      deletedMd,
    });
  } catch (error) {
    console.error('Error deleting report:', error);
    res.status(500).json({ error: 'Failed to delete report' });
  }
};
