# Incident Report Generator

A powerful, user-friendly web application for creating, managing, and exporting structured incident reports. Built with React, TypeScript, and Express.js, this tool helps teams document incidents efficiently with support for rich content, custom metadata, and multiple export formats.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Node](https://img.shields.io/badge/node-v18+-green)
![License](https://img.shields.io/badge/license-MIT-green)

## ✨ Features

### Report Creation & Management
- **Rich Content Editing** - Create reports with multiple block types:
  - Headings (H1-H4)
  - Paragraphs
  - Lists (ordered & unordered)
  - Code blocks with syntax highlighting
  - Tables with custom rows and columns
  - Images with captions (base64 embedded)
  - Incident examples
  - Description boxes
  
### Metadata Management
- **Structured Metadata** - Track essential incident information:
  - Incident ID
  - Title/Short Description
  - Caller Name
  - Date of Incident
  - Category (with custom category support)
  - Subcategory

- **Custom Categories** - Add custom incident categories:
  - Save permanently to dropdown (Add button)
  - Or use temporarily for single report (Skip button)
  - Stored in browser localStorage

### Report Editing
- **Full Edit Mode** - Load any saved report and edit all elements
- **Block Management**:
  - Edit existing blocks (text, images, code, tables, etc.)
  - Add new blocks to existing reports
  - Delete unwanted sections
  - Reorder blocks with up/down controls
- **Image Preservation** - All images are preserved in base64 format during editing
- **Smart Saving** - Save edited reports as new reports with unique timestamps

### Export Options
- **Multiple Formats**:
  - **JSON** - Complete structured data with embedded images
  - **Markdown** - Clean, readable format for documentation
  - **HTML** - Styled, printable report with embedded images

### Report Viewing & Organization
- **Report List** - Browse all saved reports with timestamps
- **Report Details** - View full report with formatted metadata and content
- **Quick Actions**:
  - Edit any report
  - Download in 3 formats
  - Delete reports with confirmation
  - Sort by date (newest first)

## 🚀 Getting Started

### Prerequisites
- Node.js (v18 or higher)
- npm or yarn

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AyoubMrani/incident-report-generator.git
   cd incident-report-generator
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Start the development server**
   ```bash
   npm run dev
   ```
   The application will be available at `http://localhost:3000`

## 📖 Usage Guide

### Creating a New Report

1. **Click "Create New"** in the top navigation
2. **Fill in Metadata**:
   - Enter Incident ID (e.g., INC0001)
   - Add a descriptive title
   - Enter caller name
   - Select date of incident
   - Choose or create a category
3. **Add Content Blocks**:
   - Click "Add Content Block"
   - Select block type from menu
   - Fill in content
   - Add more blocks as needed
4. **Generate & Save**:
   - Click "Generate & Save Report"
   - Choose download format(s)
   - File will be automatically named and saved

### Editing a Report

1. **Go to "View Reports"**
2. **Click on any report** in the list
3. **Click the "Edit" button** (blue button in header)
4. **Make changes**:
   - Edit metadata fields
   - Modify blocks
   - Add new blocks
   - Delete unwanted sections
   - Reorder with up/down arrows
5. **Save as New Report**:
   - Click "Save as New Report"
   - Confirm save
   - Get new file with new timestamp

### Custom Categories

When selecting "Other (Add Custom)" in the Category dropdown:
- **Type** your custom category name
- **Click "Add"** to save it permanently (appears in dropdown for future use)
- **Click "Skip"** to use it only for this report (not saved)

### Exporting Reports

From the Report Viewer:
- **JSON** - Full structured data (recommended for backup)
- **Markdown** - Clean format for documentation/sharing
- **HTML** - Styled, printable format with embedded images

## 📁 Project Structure

```
incident-report-generator/
├── src/
│   ├── components/
│   │   ├── BlockEditor.tsx       # Content block editor
│   │   ├── BlockRenderer.tsx     # Block display & editing
│   │   ├── MetadataEditor.tsx    # Metadata form & custom fields
│   │   ├── ExportPanel.tsx       # Save & download functionality
│   │   ├── ReportList.tsx        # List of saved reports
│   │   └── ReportViewer.tsx      # Report display & actions
│   ├── App.tsx                   # Main app component
│   ├── types.ts                  # TypeScript type definitions
│   ├── index.css                 # Global styles
│   └── main.tsx                  # Entry point
├── server.ts                     # Express.js backend
├── reports/                      # Saved reports (JSON + Markdown)
├── dist/                         # Built production files
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
└── README.md
```

## 🛠️ Tech Stack

### Frontend
- **React 19.0.0** - UI framework
- **TypeScript** - Type safety
- **Vite 6.2.0** - Build tool & dev server
- **Tailwind CSS** - Styling
- **SweetAlert2** - Beautiful alerts & confirmations
- **Lucide React** - Icons

### Backend
- **Express.js** - REST API server
- **Node.js fs module** - File I/O operations

### Storage
- **Local File System** - `./reports/` directory
- **Browser LocalStorage** - Custom fields & categories

## 🚦 Scripts

```bash
# Start development server (runs Vite HMR + Express backend)
npm run dev

# Build for production
npm run build

# Start production server
node server.ts
```

## 📝 API Endpoints

### Reports
- `POST /api/reports` - Create new report
- `GET /api/reports` - List all reports
- `GET /api/reports/content/:filename` - Get report content
- `GET /api/download?filename=:name` - Download report (JSON/MD)
- `GET /api/html?filename=:name` - Generate HTML report
- `DELETE /api/delete/:filename?` - Delete report

## 🔧 Data Storage

### File Format
Reports are saved as:
- `incident_[ID]_[TIMESTAMP].json` - Complete report data with embedded images
- `incident_[ID]_[TIMESTAMP].md` - Markdown version

### Example Report Structure
```json
{
  "metadata": {
    "incident_id": "INC0001",
    "title": "Database Connection Timeout",
    "caller": "John Doe",
    "date": "2026-05-04",
    "category": "Database",
    "subcategory": "Connection Issues"
  },
  "blocks": [
    {
      "id": "uuid-string",
      "type": "paragraph",
      "content": "Description of incident..."
    },
    {
      "id": "uuid-string",
      "type": "code",
      "language": "sql",
      "content": "SELECT * FROM table..."
    }
  ]
}
```

## 🎨 Customization

### Add New Block Types
Edit `src/types.ts` to add new block type, then implement in:
- `BlockEditor.tsx` - Add creation logic
- `BlockRenderer.tsx` - Add editing UI
- `ExportPanel.tsx` - Add export formatting

### Modify Styling
- Global styles: `src/index.css`
- Component styles: Inline Tailwind classes
- Theme: Modify Tailwind color values in components

## 🔒 Security Features

- **Directory Traversal Prevention** - DELETE endpoint validates filenames
- **Input Validation** - All API endpoints validate required fields
- **Local Storage Only** - No cloud dependencies, data stays on your machine

## 📦 Local Deployment

This application runs entirely on localhost with no external cloud dependencies:

1. **Development**:
   ```bash
   npm install
   npm run dev
   ```

2. **Production**:
   ```bash
   npm install
   npm run build
   node server.ts
   ```

Reports are stored in the `./reports/` directory on your local machine.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 💡 Tips & Tricks

- **Batch Upload** - Save multiple reports and organize by category
- **Template Reports** - Create a template and use "Edit" to create variations
- **Backup** - Regularly download reports in JSON format for backup
- **Search** - Use your browser's Ctrl+F to search within report list
- **Markdown Export** - Perfect for importing into wiki systems or documentation tools

## 🐛 Troubleshooting

### Port Already in Use
If port 3000 is already in use, modify `server.ts` to use a different port:
```typescript
const PORT = process.env.PORT || 3001;
```

### Reports Not Appearing
- Check `./reports/` directory exists
- Ensure server has read/write permissions
- Try refreshing the page (Ctrl+R)

### Images Not Saving
- Ensure image file size is reasonable (< 5MB recommended)
- Images are stored as base64, so very large images may affect performance

## 📞 Support

For issues or questions:
1. Check existing reports in the list view
2. Try the edit function to test functionality
3. Check browser console (F12) for error messages
4. Verify the server is running and accessible at `http://localhost:3000`

---

**Made with ❤️ for incident management**
