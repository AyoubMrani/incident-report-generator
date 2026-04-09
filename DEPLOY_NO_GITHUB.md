# Direct Netlify Deployment (No GitHub Required)

Your project is built and ready to deploy! Here are two methods to deploy directly:

## Method 1: Using Netlify Web Interface (Easiest)

1. **Go to https://app.netlify.com/drop** (no sign up needed to start)
   - Or create a free account at https://netlify.com and log in

2. **Drag and drop the `dist` folder** into the Netlify drop zone
   - Location: `/incident-report-generator/dist/`
   - This deploys the front-end instantly

3. **For API Functions to work:**
   - You MUST have a Netlify account (free tier works)
   - Create a new site from account dashboard
   - Add `netlify.toml` and `netlify/functions/` folder to your site
   - Configure env var `GEMINI_API_KEY` in Site Settings → Build & Deploy → Environment
   - Redeploy

## Method 2: Using Drag-and-Drop with Functions

Since you want to include API functionality:

1. **Create a deployment folder:**
   ```
   open the "dist" folder and "netlify" folder together
   ```

2. **Create at https://netlify.com:**
   - Sign in (free account)
   - Click "Add new site" → "Deploy manually"
   - Drag the entire project folder (or just dist + netlify folders)

3. **Set Environment Variables:**
   - After uploading, go to Site Settings
   - Build & Deploy → Environment variables
   - Add: `GEMINI_API_KEY` = your actual Gemini API key

## Manual Zip Upload Option

Alternatively, run this to create a ready-to-upload package:

```powershell
cd c:\Users\Baba_Noel\Desktop\incident-report-generator
Compress-Archive -Path dist, netlify, netlify.toml -DestinationPath deploy.zip
```

Then upload `deploy.zip` to Netlify's manual deployment.

## Quick Reference - What to Upload

**Minimum (Frontend only):**
- ✓ `dist/` folder

**Complete (With API):**
- ✓ `dist/` folder
- ✓ `netlify/` folder  
- ✓ `netlify.toml` file
- ✓ `package.json` file
- ✓ Set `GEMINI_API_KEY` environment variable

## Deploying Updates

After making changes:

1. Run: `npm run build`
2. Re-upload the `dist` folder (and `netlify/` if you changed functions)

**That's it! Your app will be live in seconds.** 🚀

## Notes

- Function endpoints: `/.netlify/functions/reports`, etc.
- Frontend is static and loads instantly
- Functions are serverless and scale automatically
- Free tier: 125k requests/month
