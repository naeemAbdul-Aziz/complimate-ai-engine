# CompliMate AI Engine v2.0

## Overview

The **CompliMate AI Engine v2.0** powers **CompliMate**, an AI-driven platform for contract compliance in **Ghana's petroleum sector**. This enhanced version features advanced regulation indexing, multi-regulation support, and a modern FastAPI architecture.

### Core Capabilities
It automates the analysis of contracts, ensuring they meet regulations like:

- **LI 2204** (Petroleum Local Content Regulations, 2013)
- **Act 896** (Income Tax Act, 2015)
- **Multiple regulation support** with categorization and versioning

### Technology Stack
Built with **Python** and enhanced with:
- **LlamaIndex 0.14+** for advanced document parsing and indexing
- **ChromaDB** for persistent vector storage with fallback capabilities
- **OpenAI GPT-4 & Embeddings** for intelligent analysis
- **FastAPI v2.0** with modular architecture
- **Hybrid retrieval** (BM25 + Vector search) for precise regulation matching
- **Smart indexing** with automatic change detectionI Engine

## Overview

The **CompliMate AI Engine** powers **CompliMate**, an AI-driven platform for contract compliance in **Ghana’s petroleum sector**. It automates the analysis of contracts, ensuring they meet regulations like:

- **LI 2204** (Petroleum Local Content Regulations, 2013)
- **Act 896** (Income Tax Act, 2015)

Built with **Python**, the engine leverages:
- **LlamaIndex** for contract parsing
- **ChromaDB + GPT-4 models** for storing vector embeddings
- **(LlamaIndex, ChromaDB, BM25 + Vector search for hybrid retrieval, GPT-4)** for regulation matching
- **(GPT-4 + logic)** for iolation detection 

to parse contracts and flag compliance risks efficiently.

## Key Features

### Core Analysis
- **Contract Parsing:** Advanced PDF and DOCX contract clause extraction
- **Compliance Analysis:** Hybrid search (BM25 + embeddings) + GPT for precise regulation matching
- **Multi-Regulation Support:** Handle multiple regulation files with automatic categorization
- **Performance:** Analyzes contracts in **<5 minutes**, catching **85%+ risks** (internal testing)

### v2.0 Enhancements
- **Persistent Vector Storage:** ChromaDB with automatic persistence and fallback capabilities
- **Smart Indexing:** File hash-based change detection with selective re-indexing
- **Modern API:** FastAPI v2.0 with modular router architecture and comprehensive endpoints
- **Enhanced Metadata:** Track regulation versions, categories, and modification history
- **Robust Error Handling:** Graceful fallbacks and comprehensive logging

### Scalability & Security
- **Scalability:** Processes **100 contracts/hour** (internal benchmark)
- **Security:** Fully supports **offline operation** for sensitive data protection
- **Reliability:** Multiple storage backends with automatic failover

## Installation

### Prerequisites

- Python 3.8+
- Virtual environment (recommended)
- Dependencies listed in `requirements.txt`

### Setup

**1. Clone the Repository** (private access required):
```bash
git clone https://github.com/yourusername/compli-ai-engine.git
cd compli-ai-engine
```

**2. Set Up a Virtual Environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**3. Install Dependencies:**
```bash
pip install -r requirements.txt
```

**4. Configure API Keys (if using external GPT models):**

- Add your openai API key to a `.env` file:
```env
OPEN_AI_API = your-key-here
```

- Load the key inside your code using `python-dotenv`.

## Usage

### Option 1: Command Line Interface

1. Ensure your virtual environment is activated.
2. Run the main script with a contract file:
```bash
python main.py
```
PS: A sample contract already exists in the data/contracts directory

### Option 2: API Server (v2.0)

1. Start the FastAPI server:
```bash
python scripts/run_api.py
```

2. Access the API:
- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health
- **Regulation Management:** http://localhost:8000/regulations/

### Key API Endpoints

- `GET /health` - System health and status
- `GET /regulations/` - List all regulations
- `POST /regulations/rebuild` - Rebuild regulation index
- `POST /upload` - Upload contract for analysis
- `POST /analyze` - Start compliance analysis
- `GET /analysis/{id}/status` - Check analysis status
- `GET /analysis/{id}/results` - Get analysis results

### Output

Both options will:
- Parse the contract into clauses
- Analyze clauses for compliance with regulations
- Output comprehensive reports (JSON, TXT, PDF) in the `reports/` directory

## License

This project is **proprietary**. All rights reserved. Contact us for licensing details.

## Contact

📧 **Email:** coming soon

For more about **CompliMate**, see our landing page - complighana.com
> **Powering Compliance with AI for Ghana’s Petroleum Sector** 
