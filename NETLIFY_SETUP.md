# Netlify Deployment Setup

Your project is now configured for Netlify deployment. Here's what's been set up:

## Changes Made

### 1. **netlify.toml**
- Configured build command (`npm run build`)
- Set publish directory to `dist/`
- Configured Netlify Functions location
- Added redirects for SPA routing and API endpoints

### 2. **Netlify Functions**
Replaced Express server with three serverless functions:

- **`netlify/functions/reports.ts`** - Handles POST (save reports) and GET (list reports)
- **`netlify/functions/report-content.ts`** - Retrieves report content by filename
- **`netlify/functions/report-download.ts`** - Handles file downloads

Functions use `/tmp` directory for temporary storage (note: Netlify Functions have ephemeral storage).

### 3. **package.json**
- Added `@netlify/functions` dependency for TypeScript types

## Important Notes

### File Storage Considerations
✚ Netlify Functions use `/tmp` for temporary storage (ephemeral - data is lost between deployments)
- For production, consider:
  - **Netlify Blobs** (recommended) - built-in file storage
  - **AWS S3** - external storage
  - **Database** - store metadata with actual files in storage service

### Environment Variables
1. Add your `GEMINI_API_KEY` to Netlify:
   - Go to Site Settings → Build & Deploy → Environment
   - Add `GEMINI_API_KEY` variable

2. Optional `APP_URL`:
   - Netlify auto-provides `DEPLOY_URL` environment variable

## Deployment Steps

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Build locally to test:**
   ```bash
   npm run build
   ```

3. **Connect to Netlify:**
   - Push code to GitHub/GitLab
   - Import repository in Netlify
   - Netlify detects `netlify.toml` automatically
   - Configure environment variables in Site Settings

4. **Or use Netlify CLI:**
   ```bash
   npm install -g netlify-cli
   netlify deploy
   ```

## API Endpoints

After deployment, your API endpoints will be:

- `POST /.netlify/functions/reports` - Save report
- `GET /.netlify/functions/reports` - List reports
- `GET /.netlify/functions/report-content/{filename}` - Get report content
- `GET /.netlify/functions/report-download/{filename}` - Download report file

These are routed via the `/api/*` redirect in `netlify.toml`.

## Build Status

The build configuration automatically:
- ✓ Builds React/Vite frontend
- ✓ Bundles TypeScript functions with esbuild
- ✓ Deploys static files and functions together

Your app is ready to deploy! 🚀
