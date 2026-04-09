# Vercel + Supabase Setup Guide

To integrate Vercel with Supabase for persistent file storage, I need the following information from you:

## 📋 Information Needed

### 1. **Supabase Project Details**
You'll need to create a Supabase project first. Get these from your Supabase dashboard:

- ✅ **Supabase Project URL** 
  - Example: `https://your-project.supabase.co`
  - Location: Supabase Dashboard → Settings → API → Project URL

- ✅ **Supabase Anon/Public API Key**
  - Example: `eyJhbGci...` (long string)
  - Location: Supabase Dashboard → Settings → API → Project API Keys (anon)

- ✅ **Supabase Service Role Key** (Secret)
  - For backend/API use only
  - Location: Supabase Dashboard → Settings → API → Project API Keys (service_role)
  - ⚠️ Keep this secret! Only for API functions, never expose to frontend

### 2. **How to Create Supabase Project** (if you haven't already)

1. Go to [supabase.com](https://supabase.com/)
2. Sign up or log in
3. Click "New Project"
4. Fill in:
   - Project Name: `incident-report-generator` (or your choice)
   - Database Password: Create a strong password
   - Region: Pick closest to you
5. Click "Create new project" (takes ~2 minutes)
6. Go to project dashboard → Settings → API to get credentials

## 🏗️ What I'll Set Up

Once you provide the credentials, I'll:

1. **Create Supabase Storage Bucket**
   - Create a `reports` bucket in Supabase Storage
   - Set up proper access policies

2. **Update Vercel API Functions**
   - Modify `/api/reports.ts` to upload files to Supabase
   - Modify `/api/delete.ts` to delete from Supabase
   - Modify `/api/download.ts` to download from Supabase
   - Modify `/api/reports-content.ts` to fetch from Supabase

3. **Add Environment Variables** to Vercel
   - `SUPABASE_URL` = your project URL
   - `SUPABASE_ANON_KEY` = anon key
   - `SUPABASE_SERVICE_ROLE_KEY` = service role key (secret)

4. **Update React Components**
   - Components will still work the same way
   - Backend will use Supabase instead of `/tmp`

## 📝 Benefits

✓ **Persistent Storage** - Files survive redeployments  
✓ **Scalable** - Handle large files efficiently  
✓ **Secure** - Row-level security policies  
✓ **Real-time** - Optional real-time subscriptions  
✓ **Free Tier** - Start free, pay as you grow  

## ⏭️ Next Steps

1. **Create Supabase Project** at [supabase.com](https://supabase.com/)
2. **Copy these 3 values** from Supabase Dashboard → Settings → API:
   - Project URL
   - Anon Key (public)
   - Service Role Key (secret)
3. **Send them to me** and I'll integrate everything!

## 🔐 Security Note

When you provide the Service Role Key:
- ❌ Never share it publicly
- ❌ Never commit it to git
- ✅ Only used in Vercel serverless functions (hidden backend)
- ✅ Only needed for server-side operations (delete, upload)

---

Once you have these credentials ready, message me with them and I'll complete the Supabase integration! 🚀
