import { Handler } from '@netlify/functions';
import * as fs from 'fs/promises';
import * as path from 'path';

const REPORTS_DIR = path.join('/tmp', 'reports');

export const handler: Handler = async (event) => {
  try {
    // Extract filename from multiple possible sources
    let filename = '';
    
    // Try to get from URL path
    if (event.path) {
      const parts = event.path.split('/').filter(p => p && p !== 'api' && p !== 'reports' && p !== 'download');
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

    const filePath = path.join(REPORTS_DIR, filename);
    console.log('Downloading file:', filePath);

    const content = await fs.readFile(filePath, 'utf-8');
    
    const isJson = filename.endsWith('.json');
    const contentType = isJson ? 'application/json' : 'text/markdown';
    
    return {
      statusCode: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': `attachment; filename="${filename}"`,
      },
      body: content,
      isBase64Encoded: false,
    };
  } catch (error) {
    console.error('Error downloading report:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to download report' }),
    };
  }
};
