import express from 'express';
import { createServer as createViteServer } from 'vite';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = 3000;

  // Increase payload limit for base64 images
  app.use(express.json({ limit: '50mb' }));

  const reportsDir = path.join(process.cwd(), 'reports');
  
  // Ensure reports directory exists
  try {
    await fs.access(reportsDir);
  } catch {
    await fs.mkdir(reportsDir, { recursive: true });
  }

  // API to save report
  app.post('/api/reports', async (req, res) => {
    try {
      const { report, markdown } = req.body;
      const incidentId = report.metadata.incident_id || `untitled-${Date.now()}`;
      const timestamp = Date.now();
      
      // Sanitize incident ID for filename
      const safeIncidentId = incidentId.replace(/[^a-z0-9]/gi, '_').toLowerCase();
      
      const jsonFilename = `incident_${safeIncidentId}_${timestamp}.json`;
      const mdFilename = `incident_${safeIncidentId}_${timestamp}.md`;
      
      await fs.writeFile(path.join(reportsDir, jsonFilename), JSON.stringify(report, null, 2));
      await fs.writeFile(path.join(reportsDir, mdFilename), markdown);
      
      res.json({
        success: true,
        jsonUrl: `/api/reports/download/${jsonFilename}`,
        mdUrl: `/api/reports/download/${mdFilename}`,
        jsonFilename,
        mdFilename
      });
    } catch (error) {
      console.error('Error saving report:', error);
      res.status(500).json({ error: 'Failed to save report' });
    }
  });

  // API to download report
  app.get('/api/reports/download/:filename', (req, res) => {
    const filename = req.params.filename;
    const filepath = path.join(reportsDir, filename);
    res.download(filepath);
  });

  // API to list saved reports
  app.get('/api/reports', async (req, res) => {
    try {
      const files = await fs.readdir(reportsDir);
      const jsonFiles = files.filter(f => f.endsWith('.json'));
      
      const reports = [];
      for (const file of jsonFiles) {
        try {
          const content = await fs.readFile(path.join(reportsDir, file), 'utf-8');
          const parsed = JSON.parse(content);
          const stats = await fs.stat(path.join(reportsDir, file));
          reports.push({
            filename: file,
            metadata: parsed.metadata,
            timestamp: stats.mtimeMs
          });
        } catch (err) {
          console.error(`Error reading report file ${file}:`, err);
        }
      }
      
      // Sort by newest first
      reports.sort((a, b) => b.timestamp - a.timestamp);
      res.json({ reports });
    } catch (error) {
      console.error('Error listing reports:', error);
      res.status(500).json({ error: 'Failed to list reports' });
    }
  });

  // API to get specific report content
  app.get('/api/reports/content/:filename', async (req, res) => {
    try {
      const filename = req.params.filename;
      const content = await fs.readFile(path.join(reportsDir, filename), 'utf-8');
      res.json(JSON.parse(content));
    } catch (error) {
      console.error('Error reading report content:', error);
      res.status(500).json({ error: 'Failed to read report content' });
    }
  });

  // API to delete report
  app.delete('/api/delete/:filename', async (req, res) => {
    try {
      const filename = req.params.filename;
      
      // Security: prevent directory traversal
      if (filename.includes('..') || filename.includes('/')) {
        return res.status(400).json({ error: 'Invalid filename' });
      }

      // Delete both JSON and MD files
      const jsonPath = path.join(reportsDir, filename);
      const mdPath = path.join(reportsDir, filename.replace('.json', '.md'));

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

      res.json({
        success: true,
        message: 'Report deleted successfully',
      });
    } catch (error) {
      console.error('Error deleting report:', error);
      res.status(500).json({ error: 'Failed to delete report' });
    }
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
