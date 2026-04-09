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

  if (req.method !== 'DELETE') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // Extract incident_id from query parameter
    const incident_id = req.query.incident_id as string;

    if (!incident_id) {
      console.error('No incident_id provided');
      return res.status(400).json({ error: 'Incident ID required' });
    }

    // Security: prevent directory traversal
    if (incident_id.includes('..') || incident_id.includes('/')) {
      return res.status(400).json({ error: 'Invalid incident ID' });
    }

    const folderPath = `incidents/${incident_id}`;
    console.log('Deleting folder:', folderPath);

    // List all files in the incident folder
    const { data: files, error: listError } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .list(folderPath);

    if (listError) {
      console.error(`Error listing files in ${folderPath}:`, listError);
      return res.status(404).json({ error: 'Incident folder not found' });
    }

    // Collect all file paths to delete (including subfolders)
    const filesToDelete: string[] = [];

    const collectFiles = async (folderName: string) => {
      const { data: items, error } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .list(folderName);

      if (error) throw error;

      for (const item of items) {
        if (item.is_dir) {
          await collectFiles(`${folderName}/${item.name}`);
        } else {
          filesToDelete.push(`${folderName}/${item.name}`);
        }
      }
    };

    await collectFiles(folderPath);

    console.log('Files to delete:', filesToDelete);

    if (filesToDelete.length === 0) {
      return res.status(404).json({ error: 'No files found in incident folder' });
    }

    // Delete all files
    const { error: deleteError } = await supabaseServer.storage
      .from(BUCKET_NAME)
      .remove(filesToDelete);

    if (deleteError) {
      console.error('Error deleting files:', deleteError);
      throw deleteError;
    }

    console.log(`Successfully deleted ${filesToDelete.length} files from ${folderPath}`);

    res.status(200).json({
      success: true,
      message: 'Report deleted successfully',
      deletedCount: filesToDelete.length,
      incident_id,
    });
  } catch (error) {
    console.error('Error deleting report:', error);
    res.status(500).json({ error: 'Failed to delete report' });
  }
};
