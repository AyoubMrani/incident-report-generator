# Architecture & Data Flow Diagram

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          YOUR USERS                                     │
│                    (Browser/Mobile App)                                 │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                    HTTPS Connection │ (Secure)
                                     │
                    ┌────────────────▼────────────────┐
                    │      VERCEL CDN                 │
                    │  (Static Files - Fast Global)   │
                    │  - index.html                   │
                    │  - App.css                      │
                    │  - App.js                       │
                    └────────────────┬────────────────┘
                                     │
                                     │
       ┌─────────────────────────────┴──────────────────────────────┐
       │                                                           │
       ▼                                                           ▼
┌─────────────────────────┐                             ┌──────────────────────┐
│  API FUNCTIONS          │                             │  SUPABASE STORAGE    │
│  (Vercel Serverless)    │◄──────────────────────────►│  (Persistent Files)  │
│                         │  Reads/Writes Files        │                      │
│ • /api/reports          │                             │ • Bucket: reports    │
│ • /api/reports-content  │                             │ • Your JSON files    │
│ • /api/delete           │                             │ • Your MD files      │
│ • /api/download         │                             │ • Auto Backups       │
└─────────────────────────┘                             └──────────────────────┘
```

## 📱 Data Flow: Saving a Report

```
1. User fills form & clicks "Save"
   └─► React App calls: fetch('/api/reports', { method: 'POST' })

2. Request travels to Vercel Serverless Function
   └─► /api/reports.ts receives the data

3. Function authenticates with Supabase
   └─► Uses SUPABASE_SERVICE_ROLE_KEY (from Vercel env vars)

4. Function uploads to Supabase Storage
   └─► Saves: incident_id_timestamp.json
   └─► Saves: incident_id_timestamp.md

5. Storage returns success
   └─► Function responds to browser with file URLs

6. Report appears in app
   └─► User sees "Report saved!" message

7. (Meanwhile) Files are in Supabase Storage
   └─► Persistent forever (or until deleted)
   └─► Accessible from any deployment
```

## 📖 Data Flow: Loading Reports

```
1. User clicks "View Reports"
   └─► React calls: fetch('/api/reports', { method: 'GET' })

2. Vercel function lists all files from Supabase Storage
   └─► Returns JSON with filenames & metadata

3. React displays list
   └─► User sees all saved reports

4. User clicks a report
   └─► Calls: fetch('/api/reports-content?filename=...')

5. Vercel downloads from Supabase
   └─► Returns file content

6. React displays the report
   └─► Shows incident details, metadata, blocks
```

## 🗑️ Data Flow: Deleting a Report

```
1. User clicks "Delete Report"
   └─► SweetAlert2 asks for confirmation

2. If confirmed, call: fetch('/api/delete?filename=...', { method: 'DELETE' })

3. Vercel function removes from Supabase Storage
   └─► Deletes: .json file
   └─► Deletes: .md file

4. Supabase confirms deletion
   └─► Function returns success

5. React updates list
   └─► Report disappears
```

## 🔐 Environment Variables Flow

```
                    ┌─────────────────────────────┐
                    │  .env.local (Your Computer) │
                    │  (Dev Environment)          │
                    │                             │
                    │ VITE_SUPABASE_URL           │──┐
                    │ VITE_SUPABASE_ANON_KEY      │  │
                    │ SUPABASE_URL                │  │
                    │ SUPABASE_SERVICE_ROLE_KEY   │  │
                    └─────────────────────────────┘  │
                                                      │
                          ┌───────────────────────────┘
                          │
                    ┌─────▼──────────────────────────┐
                    │  Frontend (.tsx files)          │
                    │                                │
                    │  Uses: VITE_SUPABASE_*         │
                    │  (Exposed to browser - OK!)    │
                    └────────────────────────────────┘


    ┌──────────────────────────────────────────────────────┐
    │         Vercel Dashboard (Production)               │
    │         Settings → Environment Variables            │
    │                                                      │
    │  SUPABASE_URL=...                                    │
    │  SUPABASE_SERVICE_ROLE_KEY=...                      │
    │  (Scope: Production)                                │
    │  (Secret - Never exposed!)                          │
    └────────────────────┬─────────────────────────────────┘
                         │
                    ┌────▼──────────────────────────┐
                    │  API Functions (Node.js)       │
                    │                                │
                    │  Uses: SUPABASE_*              │
                    │  (Server-side only - Safe!)   │
                    └────────────────────────────────┘
```

## 💾 Storage Comparison

### Before (Netlify - DON'T USE)
```
Create report → Save to /tmp → Deploy new version → /tmp deleted → Report lost ❌
```

### After (Supabase - CURRENT)
```
Create report → Upload to Supabase Storage → Deploy 10 times → Report still there ✅
```

## 🌍 How Files Travel

```
Your Browser
    ↓
[Report data as JSON]
    ↓
HTTPS encrypted
    ↓
Vercel (US East Coast)
    ↓
receives request
    ↓
authenticates with Supabase
    ↓
uploads to Supabase Storage (EU region)
    ↓
Storage bucket "reports"
    ↓
File stored permanently
    ↓
✅ Success response sent back
```

## 🔑 Security Layers

```
Frontend (Browser)
    └─ Has: Anon Key (limited read access)
    └─ Cannot: Delete or modify others' data

Vercel Function (Backend - Secret)
    └─ Has: Service Role Key (full admin access)
    └─ Protected: Environment variables not shown
    └─ Runs: Server-side only (not visible to users)

Supabase Storage
    └─ Has: Permission rules
    └─ Restricts: Who can read/write
    └─ Audits: All access logged
```

## 📊 Cost Breakdown (Free Tier)

```
Vercel:
├─ Serverless Functions: Free (up to 100GB bandwidth/month)
├─ Static Hosting: Free (unlimited sites)
└─ Auto-scaling: Included

Supabase:
├─ Storage: 500MB free
├─ Bandwidth: 5GB free
└─ Database: Included but not used in this app

Your App Usage (Typical):
├─ 100 reports × 200KB each = 20MB storage ✅ (free tier)
├─ Monthly bandwidth: ~1GB ✅ (free tier)
└─ Monthly requests: ~1000 ✅ (free tier)

💰 Total Cost: $0/month (free tier)
```

## 🚀 Deployment Architecture

```
code on GitHub
    ↑
    │ (you push)
    │
Vercel sees update
    │
    ├─ Runs: npm run build
    ├─ Compiles React + TypeScript
    ├─ Bundles: dist/ folder
    ├─ Auto-detects: /api functions
    │
    ├─ Reads from Vercel Dashboard:
    │  ├─ SUPABASE_URL
    │  └─ SUPABASE_SERVICE_ROLE_KEY
    │
    ├─ Deploys to CDN (global)
    ├─ Creates 4 serverless functions
    ├─ Routes API calls to functions
    │
    └─ ✅ Live in ~2-3 minutes
```

## 🎯 Key Points

1. **Frontend** - React SPA served from Vercel CDN (fast, global)
2. **API** - Serverless functions (auto-scale, pay-per-use)
3. **Storage** - Supabase (persistent, secure, backed up)
4. **Database** - Not used (could be added later)
5. **Authentication** - Not required (could be added later)

---

**Everything works together to give you:**
✅ Fast performance (CDN + serverless)
✅ Persistent data (Supabase storage)
✅ Low cost (free tier)
✅ Easy maintenance (fully managed)
✅ Professional reliability (enterprise platforms)
