import { Handler } from '@netlify/functions';
import * as fs from 'fs/promises';
import * as path from 'path';

const REPORTS_DIR = path.join('/tmp', 'reports');

// Ensure reports directory exists
async function ensureReportsDir() {
  try {
    await fs.access(REPORTS_DIR);
  } catch {
    await fs.mkdir(REPORTS_DIR, { recursive: true });
  }
}

interface ReportData {
  report: {
    metadata: {
      incident_id?: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  markdown: string;
}

export const handler: Handler = async (event) => {
  await ensureReportsDir();

  // POST - Save report
  if (event.httpMethod === 'POST') {
    try {
      const { report, markdown } = JSON.parse(event.body || '{}') as ReportData;
      const incidentId = report.metadata.incident_id || `untitled-${Date.now()}`;
      const timestamp = Date.now();

      const safeIncidentId = incidentId
        .replace(/[^a-z0-9]/gi, '_')
        .toLowerCase();

      const jsonFilename = `incident_${safeIncidentId}_${timestamp}.json`;
      const mdFilename = `incident_${safeIncidentId}_${timestamp}.md`;

      const jsonPath = path.join(REPORTS_DIR, jsonFilename);
      const mdPath = path.join(REPORTS_DIR, mdFilename);

      await fs.writeFile(jsonPath, JSON.stringify(report, null, 2));
      await fs.writeFile(mdPath, markdown);

      return {
        statusCode: 200,
        body: JSON.stringify({
          success: true,
          jsonUrl: `/api/reports/download/${jsonFilename}`,
          mdUrl: `/api/reports/download/${mdFilename}`,
          jsonFilename,
          mdFilename,
        }),
      };
    } catch (error) {
      console.error('Error saving report:', error);
      return {
        statusCode: 500,
        body: JSON.stringify({ error: 'Failed to save report' }),
      };
    }
  }

  // GET - List reports
  if (event.httpMethod === 'GET') {
    try {
      const files = await fs.readdir(REPORTS_DIR);
      const jsonFiles = files.filter((f) => f.endsWith('.json'));

      const reports = [];
      for (const file of jsonFiles) {
        try {
          const content = await fs.readFile(
            path.join(REPORTS_DIR, file),
            'utf-8'
          );
          const parsed = JSON.parse(content);
          const stats = await fs.stat(path.join(REPORTS_DIR, file));
          reports.push({
            filename: file,
            metadata: parsed.metadata,
            timestamp: stats.mtimeMs,
          });
        } catch (err) {
          console.error(`Error reading report file ${file}:`, err);
        }
      }

      reports.sort((a, b) => b.timestamp - a.timestamp);

      return {
        statusCode: 200,
        body: JSON.stringify({ reports }),
      };
    } catch (error) {
      console.error('Error listing reports:', error);
      return {
        statusCode: 500,
        body: JSON.stringify({ error: 'Failed to list reports' }),
      };
    }
  }

  return {
    statusCode: 405,
    body: JSON.stringify({ error: 'Method not allowed' }),
  };
};
