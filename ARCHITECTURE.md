# Architecture & Data Flow Diagram

## 🏗️ System Architecture (Localhost)

```
┌──────────────────────────────────────────────────────────────────┐
│                      BROWSER (Localhost)                         │
│               http://localhost:3000                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │         React App (Client-Side)                          │  │
│  │  • UI Components                                          │  │
│  │  • Form Handling                                          │  │
│  │  • Local Storage (Custom Fields)                          │  │
│  └──────────────────────┬──────────────────────────────────┘  │
│                         │                                       │
│                         │ HTTP Requests                         │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │         Express.js Server (Node.js)                      │  │
│  │         Running on http://localhost:3000                 │  │
│  │                                                            │  │
│  │  ├─ POST /api/reports          (Save report)              │  │
│  │  ├─ GET /api/reports           (List all reports)         │  │
│  │  ├─ GET /api/reports/content   (Load report content)      │  │
│  │  └─ GET /api/reports/download  (Download files)           │  │
│  └──────────────────────┬──────────────────────────────────┘  │
│                         │                                       │
│                         │ File I/O                              │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │       Local File System                                   │  │
│  │       ./reports/ folder                                   │  │
│  │       • incident_*.json files                             │  │
│  │       • incident_*.md files                               │  │
│  │       • images/ folder (embedded in JSON)                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 📱 Data Flow: Saving a Report

```
1. User fills form & clicks "Save"
   └─► React App calls: fetch('/api/reports', { method: 'POST' })

2. Request sent to Express server
   └─► /api/reports (POST handler)

3. Server receives the JSON data
   └─► Extracts incident ID, blocks, metadata

4. Server creates files in ./reports/ folder
   └─► Saves: incident_inc_XXXXXX_timestamp.json
   └─► Saves: incident_inc_XXXXXX_timestamp.md

5. Response sent back to React
   └─► Shows success message
   └─► Provides download links

6. Data persists locally
   └─► Files stay in ./reports/ folder
   └─► Available until manually deleted
```

## 💾 Data Storage

**All data stored locally** in the `./reports/` directory on your computer:
- ✅ JSON report files (complete data)
- ✅ Markdown files (formatted export)
- ✅ Embedded images (base64 in JSON)
- ✅ Custom fields (localStorage - per browser)

**No external services required:**
- ❌ No Supabase (PostgreSQL)
- ❌ No Vercel (Serverless)
- ❌ No Cloud Storage
- ❌ No Internet connection needed

## 🚀 Getting Started

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Start the dev server:**
   ```bash
   npm run dev
   ```

3. **Open in browser:**
   ```
   http://localhost:3000
   ```

4. **Reports automatically save to:** `./reports/` folder

## 📦 Files Structure

```
incident-report-generator/
├── reports/                    # ← Your data storage
│   ├── incident_inc0001_1775754589000.json
│   ├── incident_inc0001_1775754589000.md
│   └── ...
├── src/                        # React components
│   ├── components/             # UI components
│   ├── App.tsx                # Main app
│   └── main.tsx               # Entry point
├── server.ts                   # Express.js server
├── package.json
└── tsconfig.json
```

## 🔒 Security Notes

- **Localhost only** - No external connections
- **Local file storage** - Files on your computer
- **Browser local storage** - Custom fields per browser
- **No authentication** - Open to anyone on your network (if shared)
- **CORS disabled** - Only localhost access


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
