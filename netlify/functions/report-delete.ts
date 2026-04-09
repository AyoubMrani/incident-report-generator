import { Handler } from '@netlify/functions';
import * as fs from 'fs/promises';
import * as path from 'path';

const REPORTS_DIR = path.join('/tmp', 'reports');

export const handler: Handler = async (event) => {
  try {
    const filename = event.path.split('/').pop();
    
    if (!filename) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Filename required' }),
      };
    }

    // Security: prevent directory traversal
    if (filename.includes('..') || filename.includes('/')) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Invalid filename' }),
      };
    }

    // Delete both JSON and MD files
    const jsonPath = path.join(REPORTS_DIR, filename);
    const mdPath = path.join(REPORTS_DIR, filename.replace('.json', '.md'));

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

    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        message: 'Report deleted successfully',
      }),
    };
  } catch (error) {
    console.error('Error deleting report:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to delete report' }),
    };
  }
};
