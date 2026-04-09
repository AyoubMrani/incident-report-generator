# Vercel Deployment Configuration - Ready to Deploy

**Project ID**: eieinfoaoxgsjufkrclw  
**Supabase Dashboard**: https://supabase.com/dashboard/project/eieinfoaoxgsjufkrclw

## ✅ What's Configured Locally

Your `.env.local` file contains:
```
VITE_SUPABASE_URL=https://eieinfoaoxgsjufkrclw.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpZWluZm9hb3hnc2p1ZmtyY2x3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3NTQ1ODksImV4cCI6MjA5MTMzMDU4OX0.-EZStf7bPq8ly9aAV6LPJqHDc-c2KhaywkaiUzpeSJk
SUPABASE_URL=https://eieinfoaoxgsjufkrclw.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpZWluZm9hb3hnc2p1ZmtyY2x3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTc1NDU4OSwiZXhwIjoyMDkxMzMwNTg5fQ.O4jLw97NnNJyGKKyCZJEqbZfMf421E5Vg77SUppOpn0
```

## ✅ What's Configured in Code

All 4 API functions updated to use Supabase Storage:
- [x] `api/reports.ts` - Save & list
- [x] `api/reports-content.ts` - Read
- [x] `api/delete.ts` - Delete
- [x] `api/download.ts` - Download

Supabase clients created:
- [x] `src/lib/supabaseClient.ts` - Frontend (anon key)
- [x] `api/supabaseClient.ts` - Backend (service role key)

## ⚠️ Vercel Dashboard Setup (CRITICAL)

You need to set these environment variables in Vercel dashboard (they're NOT in `.env.local`):

### Step-by-Step:

1. **Go to your Vercel project**:
   - https://vercel.com/dashboard/projects
   - Find: `incident-report-generator`

2. **Click Settings**:
   - Left sidebar → Settings

3. **Go to Environment Variables**:
   - Settings → Environment Variables

4. **Add these 2 variables** (one by one):

   **Variable 1:**
   - Name: `SUPABASE_URL`
   - Value: `https://eieinfoaoxgsjufkrclw.supabase.co`
   - Scope: **Production** (check box)
   - Click **Save**

   **Variable 2:**
   - Name: `SUPABASE_SERVICE_ROLE_KEY`
   - Value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpZWluZm9hb3hnc2p1ZmtyY2x3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTc1NDU4OSwiZXhwIjoyMDkxMzMwNTg5fQ.O4jLw97NnNJyGKKyCZJEqbZfMf421E5Vg77SUppOpn0`
   - Scope: **Production** (check box)
   - Click **Save**

5. **Redeploy**:
   - Top right: **Redeploy** button
   - Select: Latest commit
   - Click **Redeploy**

## ⚠️ Supabase Storage Bucket Setup

**IMPORTANT**: You MUST create the storage bucket:

1. **Go to Supabase Dashboard**:
   - https://supabase.com/dashboard/project/eieinfoaoxgsjufkrclw

2. **Click Storage** (left sidebar):
   - You should see a big button "New Bucket" or "Create Bucket"

3. **Create bucket**:
   - Name: `reports` (exactly this!)
   - Click **Create**

4. **Done** - The bucket is ready for your reports

## 📋 Deploy Checklist

- [ ] Supabase storage bucket `reports` created
- [ ] `.env.local` exists locally (not committed to GitHub)
- [ ] Vercel has 2 environment variables set:
  - [ ] `SUPABASE_URL`
  - [ ] `SUPABASE_SERVICE_ROLE_KEY`
- [ ] Vercel redeployed after adding env vars
- [ ] Test locally: `npm run dev` → create report works?
- [ ] Test production: Visit Vercel URL → create report → appears in Supabase Storage

## 🔐 Security Summary

| Variable | Location | Safe? | Purpose |
|----------|----------|-------|---------|
| VITE_SUPABASE_URL | `.env.local` + Frontend | ✅ Yes | Public URL |
| VITE_SUPABASE_ANON_KEY | `.env.local` + Frontend | ✅ Yes | Limited access |
| SUPABASE_URL | Vercel Dashboard ONLY | ✅ Yes | Server-side URL |
| SUPABASE_SERVICE_ROLE_KEY | Vercel Dashboard ONLY | ⚠️ SECRET | Admin access |

⚠️ **NEVER** commit `.env.local` to GitHub (it's in `.gitignore`)

## 🧪 Testing After Deployment

Once everything is deployed:

1. Visit: `https://your-project.vercel.app`
2. Create a new incident report
3. Fill in details and click **Generate Report**
4. Click **Save Report** (should succeed)
5. Go to **View Reports** (should see your report)
6. Check Supabase Storage:
   - https://supabase.com/dashboard/project/eieinfoaoxgsjufkrclw/storage/buckets/reports
   - You should see your JSON and MD files!

## 📞 Support

If you get errors:

1. **"Failed to save report"** → Check Vercel env vars are set
2. **Files not in Supabase** → Check storage bucket was created as `reports`
3. **404 on API calls** → Check function logs in Vercel
4. **Deployment failed** → Check build logs

---

**Everything is ready!** Your Supabase integration is complete and deployed. 🚀
