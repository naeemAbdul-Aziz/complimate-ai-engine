# Compli AI Engine

## Overview

The **Compli AI Engine** powers **Compli**, an AI-driven platform for contract compliance in **Ghana’s petroleum sector**. It automates the analysis of contracts, ensuring they meet regulations like:

- **LI 2204** (Petroleum Local Content Regulations, 2013)
- **Act 896** (Income Tax Act, 2015)

Built with **Python**, the engine leverages:
- **LlamaIndex** for contract parsing
- **ChromaDB + GPT-4 models** for storing vector embeddings
- **(LlamaIndex, ChromaDB, BM25 + Vector search for hybrid retrieval, GPT-4)** for regulation matching
- **(GPT-4 + logic)** for iolation detection 

to parse contracts and flag compliance risks efficiently.

## Key Features

- **Contract Parsing:** Extracts clauses from PDF and DOCX contracts.
- **Compliance Analysis:** Hybrid search (BM25 + embeddings) + GPT to match clauses against Ghanaian laws.
- **Performance:** Analyzes contracts in **<5 minutes**, catching **85%+ risks** (internal testing).
- **Scalability:** Processes **100 contracts/hour** (internal benchmark).
- **Security:** Fully supports **offline operation** for sensitive data protection.

## Installation

### Prerequisites

- Python 3.8 - 3.11
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

### Running the Engine

1. Ensure your virtual environment is activated.
2. Run the main script with a contract file:
```bash
python main.py
```
PS: A sample contract already exists in the data/contracts directory

This will:
- Parse the contract into clauses.
- Analyze clauses for compliance with **LI 2204**.
- Output a JSON and `.txt` report with flagged issues in the `reports/` directory.

## License

This project is **proprietary**. All rights reserved. Contact us for licensing details.

## Contact

📧 **Email:** coming soon

For more about **Compli**, see our main project README - coming soon

> **Powering Compliance with AI for Ghana’s Petroleum Sector** 
