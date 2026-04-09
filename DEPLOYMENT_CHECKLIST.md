# Deployment Checklist

## Pre-Deployment ✅

- [x] Install dependencies: `npm install @supabase/supabase-js`
- [x] Create `.env.local` with Supabase credentials
- [x] Update all 4 API functions to use Supabase Storage
- [x] Build project: `npm run build` ✅ (success)
- [x] Verify no TypeScript errors

## Supabase Setup

- [ ] Create storage bucket named `reports` in Supabase
  - Go to: app.supabase.com → Incident Report Generator → Storage
  - Click "New Bucket" → Name: `reports` → Create

## GitHub Setup

- [ ] Initialize Git repository: `git init`
- [ ] Add all files: `git add .`
- [ ] Commit: `git commit -m "..."` 
- [ ] Create GitHub repository at github.com/new
- [ ] Add remote: `git remote add origin https://github.com/USERNAME/incident-report-generator.git`
- [ ] Push code: `git push -u origin main`

## Vercel Setup

- [ ] Sign in to vercel.com
- [ ] Click "New Project"
- [ ] Import your GitHub repository
- [ ] Set Build Command: `npm run build`
- [ ] Set Output Directory: `dist`
- [ ] Add Environment Variables:
  - [ ] `SUPABASE_URL` = `https://eieinfoaoxgsjufkrclw.supabase.co`
  - [ ] `SUPABASE_SERVICE_ROLE_KEY` = (your secret key)
- [ ] Click "Deploy"
- [ ] Wait for deployment to complete

## Post-Deployment Testing

- [ ] Visit your Vercel URL (https://xxx.vercel.app)
- [ ] Create a new report
- [ ] Save report successfully
- [ ] View reports list
- [ ] Click to view a report
- [ ] Delete a report with confirmation
- [ ] Check Supabase Storage bucket for files

## Final Steps

- [ ] Update FINAL_DEPLOYMENT_GUIDE.md with your URLs
- [ ] Test on mobile device
- [ ] Share with team
- [ ] Set up custom domain (optional)
- [ ] Monitor Vercel analytics

---

**Estimated Time**: 15-20 minutes for complete deployment
**Support**: See FINAL_DEPLOYMENT_GUIDE.md for troubleshooting
