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
      const parts = event.path.split('/').filter(p => p && p !== 'api' && p !== 'reports' && p !== 'content');
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
    console.log('Reading file:', filePath);

    const content = await fs.readFile(filePath, 'utf-8');
    
    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
      },
      body: content,
    };
  } catch (error) {
    console.error('Error reading report content:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to read report content' }),
    };
  }
};
