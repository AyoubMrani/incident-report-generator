# ✅ Correct Way to Add Environment Variables in Vercel

## ❌ DO NOT USE "Pre-production Environment"
That requires a Pro plan. We don't need it.

## ✅ CORRECT PATH:

1. **Open Vercel Dashboard**: https://vercel.com/dashboard

2. **Select your project**: `incident-report-generator`

3. **Click "Settings"** (top menu bar)

4. **Left sidebar → Click "Environment Variables"**

5. **You should see a simple form with:**
   - Name field
   - Value field  
   - Scope dropdown (set to "Production")

6. **Add Variable 1:**
   - Name: `SUPABASE_URL`
   - Value: `https://eieinfoaoxgsjufkrclw.supabase.co`
   - Scope: **Production** ✓
   - Click "Add" or "Save"

7. **Add Variable 2:**
   - Name: `SUPABASE_SERVICE_ROLE_KEY`
   - Value: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVpZWluZm9hb3hnc2p1ZmtyY2x3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTc1NDU4OSwiZXhwIjoyMDkxMzMwNTg5fQ.O4jLw97NnNJyGKKyCZJEqbZfMf421E5Vg77SUppOpn0`
   - Scope: **Production** ✓
   - Click "Add" or "Save"

8. **After adding both, go back to Deployments**

9. **Click the three dots (...) on your latest deployment**

10. **Select "Redeploy"**

---

## 🗺️ Visual Path

```
Vercel Dashboard
    ↓
incident-report-generator (your project)
    ↓
Settings (top menu)
    ↓
LEFT SIDEBAR → Environment Variables
    ↓
Add 2 production variables
    ↓
Back to "Deployments"
    ↓
Redeploy latest
```

---

**That's it!** You don't need pre-production environments. The regular Production environment variables are all you need.
