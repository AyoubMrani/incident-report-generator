# Incident Report Generator - Localhost Architecture

## 🏗️ System Architecture

This application is designed to run **entirely on localhost** with no external cloud dependencies.

```
┌──────────────────────────────────────────────────────────────────┐
│                      BROWSER (Localhost)                         │
│               http://localhost:3000                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │         React App (Client-Side)                          │  │
│  │  • UI Components (Vite + Tailwind CSS)                    │  │
│  │  • Form Handling & Report Editor                          │  │
│  │  • Local Storage (Custom Fields per browser)              │  │
│  │  • Block Editor (text, images, tables, code, etc)         │  │
│  └──────────────────────┬──────────────────────────────────┘  │
│                         │                                       │
│                         │ HTTP REST Requests                    │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │         Express.js Server (Node.js on port 3000)          │  │
│  │                                                            │  │
│  │  ├─ POST /api/reports          (Save report)              │  │
│  │  ├─ GET /api/reports           (List all reports)         │  │
│  │  ├─ GET /api/reports/content   (Load report content)      │  │
│  │  └─ GET /api/reports/download  (Download files)           │  │
│  └──────────────────────┬──────────────────────────────────┘  │
│                         │                                       │
│                         │ File System I/O                       │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │       Local File System (Your Computer)                   │  │
│  │       ./reports/ directory                                │  │
│  │       • incident_INC0001_1234567890.json                  │  │
│  │       • incident_INC0001_1234567890.md                    │  │
│  │       • (Base64 images embedded in JSON)                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 📊 Data Storage

All data is stored **locally** on your computer:

- **Reports**: `./reports/` folder
  - JSON files contain complete report data including metadata and images
  - Markdown files for formatted viewing/sharing
  - Base64-encoded images embedded directly in JSON (no separate files)

- **Custom Fields**: Browser `localStorage`
  - Per-browser storage (each browser/device has its own)
  - Survives page refresh within the same browser
  - Not synced across devices

## 🔄 Data Flow: Saving a Report

```
1. User fills out form & clicks "Save Report"
2. React app sends HTTP POST to http://localhost:3000/api/reports
3. Express server receives the request
4. Server generates unique filename with incident ID + timestamp
5. Server writes JSON and Markdown files to ./reports/ folder
6. Server responds with success + file URLs
7. React shows success modal with download buttons
8. Files persist on disk until manually deleted
```

## 🔄 Data Flow: Loading Reports

```
1. User views Reports page
2. React sends GET request to /api/reports
3. Server reads ./reports/ directory
4. Server parses JSON files to extract metadata
5. Server returns list with titles, dates, IDs
6. React displays list of reports
7. User clicks a report name
8. Server reads that specific JSON file
9. React displays the report with all content
```

## 🗑️ Data Flow: Deleting a Report

```
1. User clicks delete button on a report
2. SweetAlert2 confirmation dialog appears
3. If confirmed, React sends DELETE request
4. Server finds and deletes both .json and .md files
5. React refreshes the list
6. Deleted report no longer appears
```

## 📁 Folder Structure

```
incident-report-generator/
├── reports/                    # ← YOUR DATA (auto-created)
│   ├── incident_INC0001_1234567890.json
│   ├── incident_INC0001_1234567890.md
│   ├── incident_INC0002_1234567891.json
│   └── incident_INC0002_1234567891.md
│
├── src/
│   ├── components/             # React components
│   │   ├── App.tsx
│   │   ├── BlockEditor.tsx
│   │   ├── BlockRenderer.tsx
│   │   ├── ExportPanel.tsx
│   │   ├── MetadataEditor.tsx
│   │   ├── ReportList.tsx
│   │   └── ReportViewer.tsx
│   ├── App.tsx                # Main application
│   ├── main.tsx               # React entry point
│   ├── index.css              # Global styles
│   └── types.ts               # TypeScript types
│
├── dist/                       # Built app (after npm run build)
├── server.ts                   # Express.js server
├── vite.config.ts             # Vite build config
├── tsconfig.json              # TypeScript config
├── package.json
└── package-lock.json
```

## 🚀 Getting Started

### Prerequisites
- Node.js 16+ and npm/yarn
- A code editor (VS Code recommended)

### Installation & Running

```bash
# 1. Install dependencies
npm install

# 2. Start development server
npm run dev

# 3. Open in browser
http://localhost:3000
```

The server will:
- Serve the React app on port 3000
- Auto-reload on code changes
- Watch for file changes in `server.ts`

### Building for Production (Static)

```bash
# Build the React app for production
npm run build

# Output in ./dist/ folder
```

## 🔒 Security

**Localhost-only characteristics:**

- ✅ **No external dependencies** - Everything runs on your machine
- ✅ **No internet required** - Works completely offline
- ✅ **No authentication** - Anyone on your computer can access
- ✅ **No cloud storage** - Data stays on your disk
- ✅ **No telemetry** - Complete privacy
- ❌ **Not suitable for multi-user** - No user isolation or permissions
- ❌ **Not accessible remotely** - Only works on localhost

## 💾 Limitations

- **Single device**: Reports stored locally, not synced across computers
- **Manual backup**: You must manually backup the `./reports/` folder
- **No version control**: Overwrites without history
- **No concurrent editing**: Only works with one person at a time

## 📝 Environment Variables

No environment variables required for localhost development!

The `.env.local` file is empty by default. All configuration is built-in.

## ⚙️ Technology Stack

- **Frontend**: React 19 + TypeScript + Tailwind CSS + Vite
- **Backend**: Express.js + TypeScript
- **Data Storage**: Local file system (JSON + Markdown)
- **UI Components**: Lucide React icons, SweetAlert2 modals
- **Editor**: Custom block-based editor
