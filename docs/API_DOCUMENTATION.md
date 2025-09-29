# CompliMate API v2.0 Documentation

## Overview

The **CompliMate API v2.0** provides comprehensive endpoints for contract compliance analysis against Ghanaian regulations. This enhanced version features multi-regulation support, persistent vector storage, and advanced regulation management capabilities.

### Key Features
- **Multi-Regulation Support** - Handle multiple regulation files with categorization
- **Persistent Vector Storage** - ChromaDB integration with automatic persistence
- **Advanced Indexing** - Smart file change detection and selective re-indexing
- **Modern Architecture** - FastAPI with modular design and comprehensive documentation
- **Enhanced Analysis** - Improved compliance checking with detailed progress tracking

## Base URL
```
http://localhost:8000
```

## Interactive Documentation
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Authentication
Currently, no authentication is required. The API uses OpenAI API key configured via environment variables.

## Endpoints

### Regulation Management (New in v2.0)

#### 1. List Regulations
**GET** `/regulations/`

Get a list of all available regulations with their metadata.

**Response:**
```json
{
  "success": true,
  "message": "Regulations retrieved successfully",
  "timestamp": "2025-09-29T12:00:00.123456",
  "regulations": [
    {
      "id": "li_2204",
      "title": "Petroleum (Local Content and Local Participation) Regulations, 2013",
      "category": "petroleum",
      "description": "Local content requirements for petroleum operations",
      "version": "2013",
      "effective_date": "2013-12-31T00:00:00",
      "file_path": "data/regulations/li_2204.pdf",
      "last_updated": "2025-09-29T10:00:00.123456",
      "document_count": 22,
      "is_indexed": true
    }
  ],
  "total_count": 1
}
```

#### 2. Rebuild Regulation Index
**POST** `/regulations/rebuild`

Rebuild the regulation index, optionally forcing re-indexing of all files.

**Request Body:**
```json
{
  "force": false,
  "categories": ["petroleum", "tax"]  // optional: specific categories only
}
```

**Response:**
```json
{
  "success": true,
  "message": "Regulation index rebuilt successfully",
  "timestamp": "2025-09-29T12:00:00.123456",
  "rebuilt_regulations": ["li_2204"],
  "total_processed": 1,
  "processing_time": 12.5
}
```

#### 3. Regulation System Status
**GET** `/regulations/status`

Get the current status of the regulation management system.

**Response:**
```json
{
  "success": true,
  "message": "Regulation system status retrieved",
  "timestamp": "2025-09-29T12:00:00.123456",
  "total_regulations": 1,
  "indexed_regulations": 1,
  "storage_type": "chromadb_persistent",
  "storage_path": "C:\\path\\to\\vector_store"
}
```

### Contract Analysis

#### 4. Health Check
**GET** `/health`

Check if the API server and dependencies are running properly.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-09-29T12:00:00.123456",
  "regulation_loaded": true,
  "openai_configured": true,
  "vector_store_status": "connected",
  "total_regulations": 1,
  "indexed_documents": 22
}
```

#### 5. Upload Contract
**POST** `/upload`

Upload a contract file for analysis. Supports PDF, TXT, and DOCX files.

**Request:**
- **Content-Type:** `multipart/form-data`
- **Body:** File upload field named `file`

**Response:**
```json
{
  "message": "File uploaded successfully",
  "filename": "sample-contract.pdf",
  "file_id": "uuid-string",
  "file_path": "/path/to/uploaded/file"
}
```

**Error Responses:**
- `400`: Invalid file type
- `500`: Upload error

### 3. Start Analysis
**POST** `/analyze/{file_id}`

Start compliance analysis for an uploaded contract file.

**Parameters:**
- `file_id`: UUID of the uploaded file (from upload response)

**Response:**
```json
{
  "message": "Analysis started successfully",
  "analysis_id": "uuid-string",
  "status": "started",
  "estimated_duration": "2-5 minutes"
}
```

**Error Responses:**
- `404`: File not found
- `500`: Analysis start error

### 4. Check Analysis Status
**GET** `/status/{analysis_id}`

Check the status of a running analysis.

**Parameters:**
- `analysis_id`: UUID of the analysis (from analyze response)

**Response (In Progress):**
```json
{
  "analysis_id": "uuid-string",
  "status": "running",
  "progress": "Processing contract nodes...",
  "estimated_completion": "2025-09-28T14:35:00.123456"
}
```

**Response (Completed):**
```json
{
  "analysis_id": "uuid-string",
  "status": "completed",
  "progress": "Analysis completed successfully",
  "results": {
    "total_violations": 15,
    "high_severity": 3,
    "medium_severity": 8,
    "low_severity": 4,
    "analysis_duration": "3.2 minutes"
  },
  "report_paths": {
    "json": "/path/to/report.json",
    "text": "/path/to/report.txt",
    "pdf": "/path/to/report.pdf"
  }
}
```

**Response (Error):**
```json
{
  "analysis_id": "uuid-string",
  "status": "error",
  "progress": "Analysis failed",
  "error": "Error description"
}
```

### 5. Get Analysis Results
**GET** `/results/{analysis_id}`

Get the detailed analysis results as JSON.

**Parameters:**
- `analysis_id`: UUID of the completed analysis

**Response:**
```json
{
  "contract_name": "sample-contract.pdf",
  "regulation_file": "data/regulations/li_2204.pdf",
  "analysis_timestamp": "2025-09-28T14:32:45.123456",
  "total_prompts_sent": 25,
  "successful_responses": 24,
  "failed_responses": 1,
  "potential_issues_found": 15,
  "violations": [
    {
      "description": "The contract clause does not mention...",
      "category": "Missing Obligation",
      "regulation_ref": "Regulation 33",
      "severity": "High",
      "type": "Potential Compliance Issue",
      "contract_node_id": "uuid",
      "regulation_node_id": "uuid",
      "contract_snippet": "Contract text excerpt...",
      "regulation_snippet": "Regulation text excerpt..."
    }
  ]
}
```

### 6. Download Report
**GET** `/download/{analysis_id}/{format}`

Download the analysis report in the specified format.

**Parameters:**
- `analysis_id`: UUID of the completed analysis
- `format`: Report format (`json`, `txt`, or `pdf`)

**Response:**
- **Content-Type:** Depends on format
  - `json`: `application/json`
  - `txt`: `text/plain`
  - `pdf`: `application/pdf`
- **Body:** File content for download

### 7. List Active Analyses
**GET** `/analyses`

Get a list of all active and recent analyses.

**Response:**
```json
{
  "active_analyses": [
    {
      "analysis_id": "uuid-string",
      "contract_name": "contract1.pdf",
      "status": "running",
      "started_at": "2025-09-28T14:30:00.123456"
    }
  ],
  "total_active": 1
}
```

## Error Handling

All endpoints return appropriate HTTP status codes:

- **200**: Success
- **400**: Bad Request (invalid input)
- **404**: Not Found (file/analysis not found)  
- **500**: Internal Server Error

Error responses include a `detail` field with error description:

```json
{
  "detail": "Error description here"
}
```

## Usage Examples

### JavaScript/Frontend Integration

```javascript
// 1. Upload contract
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const uploadResponse = await fetch('/upload', {
  method: 'POST',
  body: formData
});
const uploadData = await uploadResponse.json();

// 2. Start analysis
const analyzeResponse = await fetch(`/analyze/${uploadData.file_id}`, {
  method: 'POST'
});
const analyzeData = await analyzeResponse.json();

// 3. Poll for completion
const checkStatus = async (analysisId) => {
  const statusResponse = await fetch(`/status/${analysisId}`);
  const statusData = await statusResponse.json();
  
  if (statusData.status === 'completed') {
    // Get results
    const resultsResponse = await fetch(`/results/${analysisId}`);
    const results = await resultsResponse.json();
    return results;
  } else if (statusData.status === 'error') {
    throw new Error(statusData.error);
  } else {
    // Still running, check again later
    setTimeout(() => checkStatus(analysisId), 5000);
  }
};

checkStatus(analyzeData.analysis_id);
```

### curl Examples

```bash
# Health check
curl http://localhost:8000/health

# Upload contract
curl -X POST -F "file=@contract.pdf" http://localhost:8000/upload

# Start analysis
curl -X POST http://localhost:8000/analyze/{file_id}

# Check status
curl http://localhost:8000/status/{analysis_id}

# Download PDF report
curl http://localhost:8000/download/{analysis_id}/pdf --output report.pdf
```

## Development

To start the development server:

```bash
python run_api.py
```

The server will start with auto-reload enabled for development.

## Rate Limiting

Currently, no rate limiting is implemented. Consider adding rate limiting for production use.

## Security Considerations

1. **File Upload Security**: Only PDF, TXT, and DOCX files are accepted
2. **File Storage**: Uploaded files are stored temporarily in the `uploads/` directory
3. **API Key**: OpenAI API key should be securely configured via environment variables
4. **CORS**: CORS is enabled for all origins in development mode

## Performance

- **Concurrent Analysis**: Multiple analyses can run simultaneously
- **File Size Limits**: No explicit limits set (consider adding for production)
- **Processing Time**: Typically 2-5 minutes per contract depending on size and complexity
- **Memory Usage**: Varies based on contract size and number of concurrent analyses