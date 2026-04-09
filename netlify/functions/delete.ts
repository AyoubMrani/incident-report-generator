import { Handler } from '@netlify/functions';
import * as fs from 'fs/promises';
import * as path from 'path';

const REPORTS_DIR = path.join('/tmp', 'reports');

export const handler: Handler = async (event) => {
  if (event.httpMethod !== 'DELETE') {
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' }),
    };
  }

  try {
    // Extract filename from multiple possible sources
    let filename = '';
    
    // Try to get from URL path
    if (event.path) {
      const parts = event.path.split('/').filter(p => p && p !== 'api' && p !== 'delete');
      filename = parts[parts.length - 1] || '';
    }

    // Fallback: try querystring
    if (!filename && event.queryStringParameters?.filename) {
      filename = event.queryStringParameters.filename;
    }

    if (!filename) {
      console.error('No filename provided', { path: event.path, qs: event.queryStringParameters });
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

    console.log('Deleting files:', { jsonPath, mdPath });

    let deletedJson = false;
    let deletedMd = false;

    try {
      await fs.unlink(jsonPath);
      deletedJson = true;
      console.log('Deleted JSON:', jsonPath);
    } catch (err) {
      console.error(`Error deleting JSON file ${filename}:`, err);
    }

    try {
      await fs.unlink(mdPath);
      deletedMd = true;
      console.log('Deleted MD:', mdPath);
    } catch (err) {
      console.error(`Error deleting MD file ${filename.replace('.json', '.md')}:`, err);
    }

    if (!deletedJson && !deletedMd) {
      return {
        statusCode: 404,
        body: JSON.stringify({ error: 'Files not found' }),
      };
    }

    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        message: 'Report deleted successfully',
        deletedJson,
        deletedMd,
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
