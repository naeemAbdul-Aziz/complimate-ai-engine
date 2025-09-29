## Google Firebase Studio Prompt: CompliMate AI Frontend

### Project Overview
Build a modern, responsive web application for **CompliMate AI Engine** - an AI-powered contract compliance analysis platform for Ghana's petroleum sector. The frontend should provide an intuitive interface for uploading contracts, monitoring analysis progress, and viewing detailed compliance reports.

### Core Features Required

#### 1. **Authentication & User Management**
- Firebase Authentication with email/password and Google OAuth
- Role-based access (Admin, Analyst, Viewer)
- User profile management with organization details
- Secure session management

#### 2. **File Upload & Management**
- Drag-and-drop file upload interface
- Support for PDF, TXT, and DOCX files (max 50MB)
- File validation and preview
- Upload progress indicators
- File history and management dashboard

#### 3. **Analysis Dashboard**
- Real-time analysis progress tracking
- Queue management for multiple analyses
- Status indicators (Started, Parsing, Analyzing, Completed, Failed)
- Estimated completion times
- Live progress updates using WebSockets or Server-Sent Events

#### 4. **Results & Reports Interface**
- Interactive compliance report viewer
- Violation categorization and severity indicators
- Searchable and filterable violation lists
- Side-by-side contract and regulation text comparison
- Export options (JSON, PDF, TXT)
- Report sharing and collaboration features

#### 5. **Regulation Management**
- View available regulations and their status
- Regulation indexing progress
- Category-based organization
- Metadata and statistics display

### Technical Requirements

#### Frontend Stack
- **Framework**: React 18+ with TypeScript
- **Styling**: Tailwind CSS with shadcn/ui components
- **State Management**: Zustand or Redux Toolkit
- **Real-time Updates**: Socket.io-client or WebSocket API
- **File Handling**: React Dropzone
- **Charts/Visualization**: Recharts or Chart.js
- **PDF Viewer**: react-pdf or PDF.js integration

#### Backend Integration
The frontend must integrate with our existing FastAPI backend:

**Base URL**: `http://localhost:8000` (development)

**Key API Endpoints**:
```typescript
// Health & Status
GET /health
GET /regulations/

// File Operations
POST /upload (multipart/form-data)
POST /analyze/{file_id}

// Analysis Tracking
GET /analysis/{analysis_id}/status
GET /analysis/{analysis_id}/results
GET /download/{analysis_id}/{format}

// Real-time Updates (WebSocket)
WS /ws/analysis/{analysis_id}
```

#### Firebase Services to Use
- **Hosting**: Static site hosting
- **Authentication**: User management
- **Firestore**: User preferences, analysis history metadata
- **Storage**: User documents and cached reports
- **Functions**: Middleware for API authentication
- **Analytics**: Usage tracking

### UI/UX Design Requirements

#### Design System
- Clean, professional interface suitable for legal/compliance work
- Ghana-inspired color palette with corporate blues and golds
- Accessible design (WCAG 2.1 AA compliance)
- Responsive design for desktop, tablet, and mobile

#### Key Pages/Components

1. **Landing/Login Page**
   - Company branding and feature highlights
   - Secure authentication forms
   - Demo video or screenshots

2. **Dashboard Home**
   - Recent analyses overview
   - Quick stats (total analyses, violations found, etc.)
   - Quick upload widget
   - System status indicators

3. **Upload Interface**
   - Prominent drag-and-drop area
   - File type and size indicators
   - Upload queue with progress bars
   - Batch upload support

4. **Analysis Monitor**
   - Live status cards for each analysis
   - Progress bars with time estimates
   - Cancellation options
   - Error handling and retry mechanisms

5. **Results Viewer**
   - Violation summary cards with severity indicators
   - Detailed violation list with filtering/sorting
   - Contract text highlighting
   - Regulation reference links
   - Export and sharing options

6. **Settings/Profile**
   - User preferences
   - API configuration
   - Notification settings
   - Usage statistics

#### Component Examples

```typescript
// Analysis Status Component
interface AnalysisStatus {
  id: string;
  contractName: string;
  status: 'started' | 'parsing' | 'analyzing' | 'completed' | 'failed';
  progress: string;
  estimatedCompletion?: string;
  results?: AnalysisResults;
}

// Violation Display Component
interface Violation {
  description: string;
  category: string;
  severity: 'High' | 'Medium' | 'Low';
  regulationRef: string;
  contractSnippet: string;
  type: string;
}

// File Upload Component
interface FileUpload {
  onUpload: (files: File[]) => Promise<void>;
  acceptedTypes: string[];
  maxSize: number;
  multiple: boolean;
}
```

### Real-time Features

#### WebSocket Integration
```typescript
// Analysis progress updates
const useAnalysisUpdates = (analysisId: string) => {
  const [status, setStatus] = useState<AnalysisStatus>();
  
  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/analysis/${analysisId}`);
    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      setStatus(update);
    };
    return () => ws.close();
  }, [analysisId]);
  
  return status;
};
```

### Security & Performance

#### Security
- JWT token management for API authentication
- Secure file upload with client-side validation
- HTTPS enforcement
- Input sanitization
- Rate limiting awareness

#### Performance
- Lazy loading for large reports
- Virtualized lists for violation displays
- Progressive file upload
- Optimistic UI updates
- Error boundaries and retry mechanisms

### Deployment Architecture

```
Frontend (Firebase Hosting)
     ↓ HTTPS
Backend API (Your Server)
     ↓
ChromaDB + OpenAI
```

#### Environment Configuration
```typescript
// Environment variables
interface Config {
  API_BASE_URL: string;
  WS_BASE_URL: string;
  FIREBASE_CONFIG: FirebaseConfig;
  MAX_FILE_SIZE: number;
  ALLOWED_FILE_TYPES: string[];
}
```

### Development Workflow

1. **Setup Phase**
   - Initialize Firebase project
   - Configure authentication providers
   - Set up Firestore security rules
   - Create CI/CD pipeline

2. **Core Development**
   - Implement authentication flow
   - Build file upload system
   - Create analysis monitoring
   - Develop results viewer

3. **Integration & Testing**
   - API integration testing
   - Real-time feature testing
   - Cross-browser compatibility
   - Performance optimization

4. **Deployment**
   - Firebase hosting setup
   - Environment configuration
   - SSL certificate management
   - Monitoring and analytics

### Success Metrics
- File upload success rate > 99%
- Analysis completion tracking accuracy
- User session duration
- Report export usage
- Error rates and response times

This frontend should provide a seamless, professional experience for legal professionals analyzing contract compliance while leveraging Firebase's scalability and your existing FastAPI backend.