# Final Deployment Guide: Vercel + Supabase

Your Incident Report Generator is now configured for production deployment with persistent storage using Supabase.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Your Application                          │
│                    (Static React SPA)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                ┌──────▼──────────────────┐
                │   Vercel (Hosting)      │
                │  - Static Files (/dist) │
                │  - API Functions (/api) │
                └──────┬───────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
    ┌───▼────────────┐      ┌────────▼────────┐
    │  Supabase      │      │  Supabase       │
    │  Storage       │      │  Database       │
    │  (Reports)     │      │  (Optional)     │
    └────────────────┘      └─────────────────┘
```

## Step-by-Step Deployment

### Phase 1: Prepare Your Git Repository

1. **Initialize Git** (if not already done):
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Incident Report Generator with Supabase"
   ```

2. **Create a GitHub repository**:
   - Go to [github.com/new](https://github.com/new)
   - Create a new repository (name: `incident-report-generator`)
   - Follow instructions to push your local code:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/incident-report-generator.git
   git branch -M main
   git push -u origin main
   ```

3. **Verify .gitignore** includes these (already configured):
   ```
   .env.local
   .env*
   node_modules/
   dist/
   ```

### Phase 2: Create Supabase Storage Bucket

Your Supabase project is already created. Now set up the storage bucket:

1. **Go to [Supabase Dashboard](https://app.supabase.com)**
2. **Select** "Incident Report Generator" project
3. **Navigate to Storage** (left sidebar)
4. **Click "New Bucket"**
5. **Configure**:
   - Bucket name: `reports`
   - Click **Create Bucket**

✅ Your storage bucket is ready!

### Phase 3: Connect to Vercel and Deploy

1. **Go to [vercel.com](https://vercel.com)**
2. **Sign up** (or login with GitHub)
3. **Click "New Project"**
4. **Select your GitHub repository**:
   - Search for `incident-report-generator`
   - Click **Import**
5. **Configure Project**:
   - Framework Preset: **Vite** (auto-detected)
   - Root Directory: `./` (default)
   - Build Command: `npm run build` (auto-filled)
   - Output Directory: `dist` (auto-filled)

6. **Add Environment Variables** (CRITICAL):
   - Click **Environment Variables**
   - Add three variables:

   | Name | Value | Scope |
   |------|-------|-------|
   | `SUPABASE_URL` | `https://eieinfoaoxgsjufkrclw.supabase.co` | Production |
   | `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpZWluZm9hb3hnc2p1ZmtyY2x3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTc1NDU4OSwiZXhwIjoyMDkxMzMwNTg5fQ.O4jLw97NnNJyGKKyCZJEqbZfMf421E5Vg77SUppOpn0` | Production |

   ⚠️ Make sure these are saved!

7. **Click "Deploy"**
8. **Wait for build** to complete (approximately 2-3 minutes)
9. **Get your URL**: Once deployed, Vercel gives you a URL like:
   ```
   https://incident-report-generator-xxxxx.vercel.app
   ```

✅ Your app is now deployed and live!

### Phase 4: Test Your Deployment

1. **Visit your app**: `https://your-project.vercel.app`
2. **Test create report**:
   - Fill in incident details
   - Click "Generate Report"
   - Save the report
   - Verify no errors appear

3. **Test list reports**:
   - Click "View Reports"
   - Your saved report should appear
   - Verify timestamp and metadata display

4. **Test view/delete**:
   - Click the report to view details
   - Click delete with SweetAlert confirmation
   - Verify it's removed from the list

### Phase 5: Verify Supabase Storage

1. **Go back to [Supabase Dashboard](https://app.supabase.com)**
2. **Select** "Incident Report Generator"
3. **Navigate to Storage**
4. **Open `reports` bucket**
5. **You should see** your generated files:
   - `incident_something_1775754589000.json`
   - `incident_something_1775754589000.md`

✅ Files are persisted in Supabase!

### Phase 6: Enable Automatic Deployments (Optional but Recommended)

1. **In Vercel dashboard**, your project is already connected to GitHub
2. **Every time you push to `main` branch**, Vercel automatically redeploys
3. **Test**: Make a small code change locally:
   ```bash
   git add .
   git commit -m "Test automatic deployment"
   git push
   ```
4. **Watch Vercel dashboard** - it should redeploy automatically

## Important Notes

### Environment Variables Recap

**Frontend (safe to expose)**:
- `VITE_SUPABASE_URL` → Supabase project URL
- `VITE_SUPABASE_ANON_KEY` → Limited read-only permissions

**Backend (SECRET)**:
- `SUPABASE_SERVICE_ROLE_KEY` → Full admin access (never expose!)
- Never commit to version control
- Only configure in Vercel dashboard

### File Locations After Deploy

- **Frontend code**: Deployed to Vercel CDN (automatically compressed, cached globally)
- **API functions**: Running on Vercel Serverless (auto-scales, pay-per-request)
- **Report files**: Stored in Supabase Storage (persistent, accessible 24/7)

### Costs

**Free tier includes**:
- Vercel: 100GB bandwidth/month, unlimited deployments
- Supabase: 500MB storage, 5GB bandwidth
- This app easily fits within free limits

### Next Steps (Optional Enhancements)

1. **Custom Domain**:
   - In Vercel: Settings → Domains
   - Add your domain (requires DNS configuration)

2. **Database Integration** (future):
   - Add Supabase PostgreSQL for metadata indexing
   - Create custom queries/analytics

3. **User Authentication**:
   - Use Supabase Auth for user-specific reports
   - Add Supabase RLS (Row Level Security)

4. **Backup Strategy**:
   - Supabase automatically backs up daily (included in free tier)
   - Configure additional backups if needed

## Troubleshooting

**Problem**: "Failed to save report" error
- Check Vercel Function Logs: Dashboard → Deployments → [Latest] → Function Logs
- Verify environment variables are set in Vercel
- Check Supabase Storage bucket exists and is accessible

**Problem**: Files don't appear in Supabase Storage
- Verify `SUPABASE_SERVICE_ROLE_KEY` is correct
- Check bucket name is exactly `reports` (lowercase)
- Review Supabase activity logs

**Problem**: 404 errors on file operations
- Check Network tab in browser DevTools
- Verify API function URLs are correct
- Check Vercel function deployment status

**Problem**: Changes don't appear after pushing
- Git push might have failed silently
- Check GitHub Actions logs
- Try manual redeploy in Vercel dashboard: Settings → Git → Redeploy

## Support Resources

- [Vercel Docs](https://vercel.com/docs)
- [Supabase Docs](https://supabase.com/docs)
- [Vite Docs](https://vitejs.dev/)

---

**Deployment Status**: ✅ Ready to deploy
**Last Updated**: April 9, 2026
**Repository**: [GitHub Link - Add after pushing]
**Live App**: [Your Vercel URL - Add after deployment]
