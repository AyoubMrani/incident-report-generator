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
    [key: string]: unknown;
  };
  markdown: string;
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
      const incidentId = report.metadata.incident_id || `untitled-${Date.now()}`;
      const timestamp = Date.now();

      const safeIncidentId = incidentId
        .replace(/[^a-z0-9]/gi, '_')
        .toLowerCase();

      const jsonFilename = `incident_${safeIncidentId}_${timestamp}.json`;
      const mdFilename = `incident_${safeIncidentId}_${timestamp}.md`;

      console.log('Uploading to Supabase:', { BUCKET_NAME, jsonFilename, mdFilename });

      // Upload JSON file to Supabase
      const { error: jsonError } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .upload(jsonFilename, JSON.stringify(report, null, 2), {
          contentType: 'application/json',
        });

      if (jsonError) {
        console.error('JSON upload error:', jsonError);
        throw jsonError;
      }

      // Upload Markdown file to Supabase
      const { error: mdError } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .upload(mdFilename, markdown, {
          contentType: 'text/markdown',
        });

      if (mdError) {
        console.error('MD upload error:', mdError);
        throw mdError;
      }

      console.log('Upload successful!');
      res.status(200).json({
        success: true,
        jsonUrl: `/api/download?filename=${jsonFilename}`,
        mdUrl: `/api/download?filename=${mdFilename}`,
        jsonFilename,
        mdFilename,
      });
    } catch (error) {
      console.error('Error saving report:', error);
      res.status(500).json({ error: 'Failed to save report', details: String(error) });
    }
  }

  // GET - List reports
  else if (req.method === 'GET') {
    try {
      const { data: files, error } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .list();

      if (error) throw error;

      const reports = [];
      for (const file of files) {
        if (file.name.endsWith('.json')) {
          try {
            const { data, error: readError } = await supabaseServer.storage
              .from(BUCKET_NAME)
              .download(file.name);

            if (readError) throw readError;

            const text = await data.text();
            const parsed = JSON.parse(text);
            reports.push({
              filename: file.name,
              metadata: parsed.metadata,
              timestamp: new Date(file.updated_at).getTime(),
            });
          } catch (err) {
            console.error(`Error reading report file ${file.name}:`, err);
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
