import logging
import os
import tempfile

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile

# Import your engine modules
from engine import parsing, retrieval, violation
from reporting import report_generator

# Load environment variables
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY is not set in .env")

# Initialize FastAPI app
app = FastAPI()

# --- API Endpoints ---


@app.post("/analyze_contract/")
async def analyze_contract(file: UploadFile = File(...)):
    """
    Analyzes a contract file uploaded by the user.
    """
    logging.info(f"Received file: {file.filename}")

    try:
        # 1. Save the uploaded file temporarily
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file.filename
        ) as temp_file:
            file_content = await file.read()
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        logging.info(f"Saved temporary file to: {temp_file_path}")

        # 2. Process the contract using the engine
        contract_nodes = parsing.parse_contract(temp_file_path)
        if not contract_nodes:
            raise HTTPException(status_code=400, detail="Failed to parse contract.")

        regulation_index = retrieval.load_or_create_regulation_index(
            retrieval.load_regulation_text("data/regulations/li_2204.pdf")
        )
        if not regulation_index:
            raise HTTPException(
                status_code=500, detail="Failed to load regulation index."
            )

        all_violations = []
        batch_size = 5

        for i in range(0, len(contract_nodes), batch_size):
            batch_nodes = contract_nodes[i : i + batch_size]
            for node in batch_nodes:
                try:
                    relevant_regs = retrieval.find_relevant_regulations(
                        node, regulation_index
                    )
                    if relevant_regs:
                        violations = violation.detect_violations(
                            node, relevant_regs, openai_api_key
                        )
                        if violations:
                            all_violations.extend(violations)
                except Exception as node_error:
                    logging.error(
                        f"Error processing node in {file.filename}: {node_error}"
                    )
                    continue

        # 3. Generate the report
        contract_name = os.path.splitext(file.filename)[0]
        report_data = {
            "contract_name": contract_name,
            "violations": all_violations,
        }

        os.makedirs("reports", exist_ok=True)
        report_path = f"reports/{contract_name}_report.json"
        report_generator.generate_report(report_data, report_path)

        return {"message": "Contract analysis complete", "report_path": report_path}

    except Exception as e:
        logging.error(f"Error processing file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 4. Clean up temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logging.info(f"Deleted temporary file: {temp_file_path}")


# Health Check Endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
