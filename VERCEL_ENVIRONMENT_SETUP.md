# Vercel + Supabase Integration Guide

This app now uses **Supabase Storage** for persistent file storage instead of ephemeral Vercel `/tmp` storage.

## Environment Variables

### Frontend (.env.local - Local Development)
These variables are exposed to the frontend but safe to use (anon key has limited permissions):
```
VITE_SUPABASE_URL=https://eieinfoaoxgsjufkrclw.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpZWluZm9hb3hnc2p1ZmtyY2x3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3NTQ1ODksImV4cCI6MjA5MTMzMDU4OX0.-EZStf7bPq8ly9aAV6LPJqHDc-c2KhaywkaiUzpeSJk
```

### Backend (Vercel Environment Variables)
These must be configured in Vercel for production. The **Service Role Key is SECRET** and should never be exposed publicly.

**Steps to add to Vercel:**

1. Go to your Vercel project dashboard
2. Navigate to **Settings** → **Environment Variables**
3. Add these three variables:

| Name | Value |
|------|-------|
| `SUPABASE_URL` | `https://eieinfoaoxgsjufkrclw.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpZWluZm9hb3hnc2p1ZmtyY2x3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTc1NDU4OSwiZXhwIjoyMDkxMzMwNTg5fQ.O4jLw97NnNJyGKKyCZJEqbZfMf421E5Vg77SUppOpn0` |

4. Click **Save**
5. Trigger a redeploy to apply the variables

## Storage Setup

The reports are stored in a Supabase Storage bucket named **`reports`**.

### Creating the Bucket (if not already created):

1. Go to [Supabase Dashboard](https://app.supabase.com).
2. Select your project "Incident Report Generator"
3. Navigate to **Storage** in the left sidebar
4. Click **New Bucket**
5. Name it: `reports`
6. **Uncheck** "Make it private" (or keep it private and use RLS policies)
7. Click **Create**

### Bucket Objects:
- JSON files: `incident_{sanitized_id}_{timestamp}.json` - Full report data
- Markdown files: `incident_{sanitized_id}_{timestamp}.md` - Export format

## API Functions

All Vercel API functions now use Supabase Storage via the `supabaseServer` client:

- **`/api/reports`** - POST to save, GET to list all reports
- **`/api/reports-content`** - GET report JSON by filename
- **`/api/delete`** - DELETE report and markdown files
- **`/api/download`** - GET file download with proper headers

## Local Development

1. **Copy `.env.local.example` to `.env.local`** and add your credentials
2. **Run `npm run dev`** to start the development server
3. Reports are saved to the local `./reports` directory (filesystem)
4. Both frontend and backend can access Supabase using credentials from `.env.local`

## Production Deployment

1. **GitHub**: Push your code to GitHub (ensure `.env.local` is in `.gitignore`)
2. **Vercel**: Connect your GitHub repo to Vercel
3. **Environment Variables**: Configure Supabase credentials in Vercel dashboard
4. **Redeploy**: Vercel will automatically build and deploy with the new environment variables

## Security Notes

⚠️ **IMPORTANT:**
- `VITE_SUPABASE_ANON_KEY` is exposed to the frontend - this is intentional and safe (limited read-only access)
- `SUPABASE_SERVICE_ROLE_KEY` is the secret - never expose this in frontend code or version control
- Keep `.env.local` in `.gitignore` (already configured)
- Only set backend variables in Vercel's secure environment variable settings

## Testing

After deployment to Vercel:

1. Visit your app: `https://your-project.vercel.app`
2. Try creating a new report
3. Save it - files should upload to Supabase Storage
4. View/delete reports to verify the API works
5. Check Vercel Function Logs for debugging: Dashboard → Deployments → Function Logs
