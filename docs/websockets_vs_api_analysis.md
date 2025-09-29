# WebSockets vs API Calls: Analysis for CompliMate AI

## Overview
This document analyzes when to use WebSockets versus traditional REST API calls for the CompliMate AI Engine frontend, considering the specific use cases of contract analysis and compliance reporting.

## When to Use WebSockets

### ✅ **Ideal Use Cases for CompliMate AI**

#### 1. **Real-time Analysis Progress**
```typescript
// WebSocket: Perfect for live progress updates
const ws = new WebSocket(`ws://api/analysis/${analysisId}/progress`);
ws.onmessage = (event) => {
  const progress = JSON.parse(event.data);
  // Update: "Parsing contract..." → "Analyzing clause 15/67..." → "Generating report..."
  updateProgressBar(progress.percentage, progress.message);
};
```

**Why WebSockets**: 
- Analysis can take 2-5 minutes
- Users need continuous feedback
- Eliminates need for polling every few seconds
- Provides instant status updates

#### 2. **Multi-user Collaboration**
```typescript
// Multiple analysts working on same project
ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  if (notification.type === 'analysis_completed') {
    showNotification(`${notification.user} completed analysis of ${notification.contract}`);
  }
};
```

#### 3. **System-wide Notifications**
```typescript
// Real-time system alerts
ws.onmessage = (event) => {
  const alert = JSON.parse(event.data);
  if (alert.type === 'regulation_updated') {
    showBanner('New regulation indexed. Refresh to see updates.');
  }
};
```

### ❌ **Poor Use Cases for WebSockets**

#### 1. **One-time Data Fetching**
```typescript
// DON'T use WebSocket for this
const regulations = await fetch('/api/regulations').then(r => r.json());
```

#### 2. **File Uploads**
```typescript
// DON'T use WebSocket for file uploads
const formData = new FormData();
formData.append('file', file);
await fetch('/api/upload', { method: 'POST', body: formData });
```

## When to Use REST API Calls

### ✅ **Ideal Use Cases for CompliMate AI**

#### 1. **CRUD Operations**
```typescript
// Get regulations list
const regulations = await fetch('/api/regulations').then(r => r.json());

// Upload contract
const uploadResult = await fetch('/api/upload', {
  method: 'POST',
  body: formData
});

// Download report
const blob = await fetch(`/api/download/${analysisId}/pdf`).then(r => r.blob());
```

#### 2. **Authentication & Session Management**
```typescript
// Login
const authResult = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password })
});
```

#### 3. **Configuration & Settings**
```typescript
// Update user preferences
await fetch('/api/user/preferences', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(preferences)
});
```

## Hybrid Approach: Best of Both Worlds

### **CompliMate AI Recommended Architecture**

```typescript
class CompliMateAPI {
  private wsConnections: Map<string, WebSocket> = new Map();
  
  // REST for data operations
  async uploadContract(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return fetch('/api/upload', { method: 'POST', body: formData })
      .then(r => r.json());
  }
  
  async startAnalysis(fileId: string): Promise<AnalysisResponse> {
    return fetch(`/api/analyze/${fileId}`, { method: 'POST' })
      .then(r => r.json());
  }
  
  // WebSocket for real-time updates
  subscribeToAnalysis(analysisId: string, onUpdate: (progress: AnalysisProgress) => void) {
    const ws = new WebSocket(`ws://api/analysis/${analysisId}/progress`);
    ws.onmessage = (event) => onUpdate(JSON.parse(event.data));
    this.wsConnections.set(analysisId, ws);
    return () => {
      ws.close();
      this.wsConnections.delete(analysisId);
    };
  }
}
```

## Implementation Strategy

### **Phase 1: Core API Integration (REST Only)**
Start with REST APIs for all operations:

```typescript
// Polling-based progress tracking (temporary)
const pollAnalysisStatus = async (analysisId: string) => {
  const checkStatus = async () => {
    const status = await fetch(`/api/analysis/${analysisId}/status`).then(r => r.json());
    updateUI(status);
    
    if (status.status === 'completed' || status.status === 'failed') {
      clearInterval(interval);
    }
  };
  
  const interval = setInterval(checkStatus, 2000); // Poll every 2 seconds
  return interval;
};
```

### **Phase 2: Add WebSocket Enhancement**
Upgrade to WebSockets for real-time features:

```typescript
// Enhanced with WebSocket
const trackAnalysisProgress = (analysisId: string) => {
  // Try WebSocket first
  try {
    const ws = new WebSocket(`ws://api/analysis/${analysisId}/progress`);
    ws.onmessage = (event) => updateUI(JSON.parse(event.data));
    ws.onerror = () => {
      // Fallback to polling if WebSocket fails
      console.warn('WebSocket failed, falling back to polling');
      pollAnalysisStatus(analysisId);
    };
  } catch (error) {
    // Fallback to polling
    pollAnalysisStatus(analysisId);
  }
};
```

## Performance Comparison

### **Polling vs WebSocket for Analysis Progress**

| Aspect | REST Polling (2s interval) | WebSocket |
|--------|---------------------------|-----------|
| **Network Requests** | 150 requests (5min analysis) | 1 connection + real-time updates |
| **Latency** | 0-2 seconds delay | Instant (~10ms) |
| **Server Load** | High (150 HTTP requests) | Low (1 persistent connection) |
| **Bandwidth** | High (HTTP headers + JSON) | Low (JSON only) |
| **Battery Usage** | Higher (mobile) | Lower |
| **Complexity** | Simple | Moderate |

### **Cost Analysis (Firebase/Server)**

```typescript
// Cost comparison for 100 concurrent analyses
const costs = {
  polling: {
    requests: 100 * 150, // 15,000 HTTP requests
    bandwidth: '~1.5MB per analysis',
    serverCPU: 'High (processing 15k requests)'
  },
  websocket: {
    connections: 100, // 100 WebSocket connections
    bandwidth: '~50KB per analysis',
    serverCPU: 'Low (maintaining connections)'
  }
};
```

## Technical Implementation

### **WebSocket Connection Management**

```typescript
class WebSocketManager {
  private connections: Map<string, WebSocket> = new Map();
  private reconnectAttempts: Map<string, number> = new Map();
  
  connect(analysisId: string, onMessage: (data: any) => void) {
    const ws = new WebSocket(`ws://api/analysis/${analysisId}/progress`);
    
    ws.onopen = () => {
      console.log(`Connected to analysis ${analysisId}`);
      this.reconnectAttempts.set(analysisId, 0);
    };
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onMessage(data);
      
      // Auto-close on completion
      if (data.status === 'completed' || data.status === 'failed') {
        this.disconnect(analysisId);
      }
    };
    
    ws.onclose = () => {
      this.handleReconnect(analysisId, onMessage);
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    this.connections.set(analysisId, ws);
  }
  
  private handleReconnect(analysisId: string, onMessage: (data: any) => void) {
    const attempts = this.reconnectAttempts.get(analysisId) || 0;
    
    if (attempts < 3) {
      setTimeout(() => {
        console.log(`Reconnecting to analysis ${analysisId} (attempt ${attempts + 1})`);
        this.reconnectAttempts.set(analysisId, attempts + 1);
        this.connect(analysisId, onMessage);
      }, Math.pow(2, attempts) * 1000); // Exponential backoff
    } else {
      console.warn(`Max reconnection attempts reached for ${analysisId}`);
      // Fallback to polling
    }
  }
  
  disconnect(analysisId: string) {
    const ws = this.connections.get(analysisId);
    if (ws) {
      ws.close();
      this.connections.delete(analysisId);
      this.reconnectAttempts.delete(analysisId);
    }
  }
}
```

## Recommendations for CompliMate AI

### **Use WebSockets for:**
1. ✅ **Analysis progress tracking** - Real-time updates during 2-5 minute analysis
2. ✅ **System notifications** - Regulation updates, system status
3. ✅ **Multi-user collaboration** - Show when other users complete analyses
4. ✅ **Queue status** - Real-time queue position updates

### **Use REST APIs for:**
1. ✅ **File uploads** - Better support for multipart/form-data
2. ✅ **Authentication** - Standard HTTP auth flows
3. ✅ **CRUD operations** - Regulations list, user settings
4. ✅ **Report downloads** - File streaming capabilities
5. ✅ **One-time queries** - Health checks, static data

### **Implementation Timeline**

**Week 1-2: REST Foundation**
- Implement all core functionality with REST APIs
- Use polling for progress tracking (simple but functional)

**Week 3-4: WebSocket Enhancement**
- Add WebSocket support for real-time progress
- Implement fallback mechanisms
- Add connection management

**Week 5+: Advanced Features**
- Multi-user notifications
- Real-time collaboration features
- Performance optimization

This approach ensures you have a working application quickly while building toward an optimal real-time experience.