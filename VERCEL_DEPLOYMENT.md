# Vercel Deployment Setup

Your project is now configured for **Vercel** deployment! Here's everything you need to know:

## Project Structure for Vercel

```
incident-report-generator/
├── api/                          # Serverless API functions
│   ├── reports.ts               # POST/GET reports
│   ├── reports-content.ts       # GET report content
│   ├── delete.ts                # DELETE reports
│   └── download.ts              # Download reports
├── dist/                         # Built React app
├── src/                          # React source code
├── vercel.json                  # Vercel configuration
└── package.json
```

## Deployment Steps

### 1. **Install Vercel CLI** (Optional but recommended)
```bash
npm install -g vercel
```

### 2. **Option A: Deploy via Git (Easiest)**
- Push code to GitHub repository
- Go to [vercel.com](https://vercel.com/)
- Click "New Project" → Import Git repository
- Vercel auto-detects and deploys automatically
- Set environment variables in Vercel dashboard:
  - `GEMINI_API_KEY` = your Gemini API key

### 3. **Option B: Deploy via CLI**
```bash
cd incident-report-generator
vercel --prod
```

## ⚙️ API Endpoints

After deployment to `your-domain.vercel.app`:

- **List Reports**: `GET https://your-domain.vercel.app/api/reports`
- **Get Report Content**: `GET https://your-domain.vercel.app/api/reports-content?filename=...`
- **Save Report**: `POST https://your-domain.vercel.app/api/reports`
- **Delete Report**: `DELETE https://your-domain.vercel.app/api/delete?filename=...`
- **Download Report**: `GET https://your-domain.vercel.app/api/download?filename=...`

## 📝 Environment Variables

Configure these in Vercel Project Settings → Environment Variables:

```
GEMINI_API_KEY = your_gemini_api_key_here
```

## ⚠️ Storage Limitation

**Important:** Vercel's `/tmp` directory is ephemeral (temporary). Reports created will be lost when:
- You redeploy
- Function instance is recycled
- After ~15 minutes of inactivity

## 💾 For Persistent Storage, Use:

### Option 1: **Vercel Postgres** (Recommended for production)
- Built-in database with Vercel
- Pay-as-you-go pricing
- [Setup Guide](https://vercel.com/docs/storage/postgres)

### Option 2: **Vercel KV** (Redis-based)
- Fast in-memory storage
- Great for frequently accessed data
- [Setup Guide](https://vercel.com/docs/storage/vercel-kv)

### Option 3: **AWS S3 + DynamoDB**
- More control over architecture
- Industry standard
- Requires AWS account

## 🚀 Quick Start to Deploy

```bash
# 1. Install Vercel CLI (if using CLI method)
npm install -g vercel

# 2. From project directory
cd incident-report-generator

# 3. Deploy to production
vercel --prod
```

## 🔍 Troubleshooting

**Reports not saving?**
- Check Vercel Function logs in dashboard
- Verify environment variables are set
- Check browser console for errors

**Reports disappear after deployment?**
- This is expected with `/tmp` storage
- Use persistent storage solution (see above)

**API endpoints not working?**
- Verify URLs use query parameters: `?filename=...`
- Check Vercel Function logs
- Ensure file exists before trying to delete/download

## 📚 Useful Vercel Commands

```bash
# Deploy to preview
vercel

# Deploy to production
vercel --prod

# View logs
vercel logs

# List deployments
vercel list

# Remove deployment
vercel remove
```

---

Your app is ready for Vercel! 🎉
