# main.py
import os
import asyncio
import logging # Import logging
import datetime # For report naming
from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from PyPDF2 import PdfReader

# Import engine modules
from engine.parsing import parse_contract
from engine.retrieval import find_relevant_regulations
from engine.violation import create_violation_prompt, process_batch_violation_responses

# Import reporting functions
from reporting.report_generator import generate_report, generate_text_report, generate_pdf_report

# --- Basic Logging Configuration ---
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper() # Default to INFO, changeable via env var
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=log_level, format=log_format)
logger = logging.getLogger(__name__) # Get logger for main module
# -----------------------------------

# Constants
REGULATION_FILE = "data/regulations/li_2204.pdf"
CONTRACT_FOLDER = "data/contracts"
REPORTS_FOLDER = "reports"

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

def load_regulation(file_path):
    """Loads and preprocesses the regulation text from a PDF file."""
    logger.info(f"Loading regulation file: {file_path}")
    text = ""
    try:
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            num_pages = len(reader.pages)
            logger.debug(f"Reading {num_pages} pages from {file_path}")
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                else:
                     logger.warning(f"No text extracted from page {i+1} of {file_path}")
        logger.info(f"Regulation loaded successfully ({len(text)} characters): {file_path}")
        return text
    except FileNotFoundError:
        logger.error(f"Regulation file not found: {file_path}")
        return ""
    except Exception as e:
        logger.exception(f"Error reading regulation file {file_path}: {e}")
        return ""

async def main():
    """Main async function to run the contract compliance analysis."""
    logger.info("--- Starting Contract Compliance Analysis ---")

    if not openai_api_key:
        logger.critical("OPENAI_API_KEY not found in environment variables. Exiting.")
        return

    # --- Setup ---
    if not os.path.exists(REPORTS_FOLDER):
        try:
            os.makedirs(REPORTS_FOLDER)
            logger.info(f"Created reports directory: {REPORTS_FOLDER}")
        except OSError as e:
             logger.critical(f"Failed to create reports directory {REPORTS_FOLDER}: {e}. Exiting.")
             return


    logger.info("Initializing LLM and Embedding models...")
    try:
        # Adjust timeout as needed for potentially longer prompts/responses
        Settings.llm = OpenAI(model="gpt-4", api_key=openai_api_key, request_timeout=180.0)
        Settings.embed_model = OpenAIEmbedding(model="text-embedding-ada-002", api_key=openai_api_key)
        logger.info("LLM and Embedding models initialized.")
    except Exception as e:
        logger.critical(f"Error initializing OpenAI models: {e}. Exiting.")
        return

    # --- Load Regulation & Create Index ---
    regulation_text = load_regulation(REGULATION_FILE)
    if not regulation_text:
        logger.critical("Failed to load regulation text. Exiting.")
        return

    logger.info("Creating regulation index...")
    try:
        regulation_document = Document(text=regulation_text, doc_id=REGULATION_FILE)
        regulation_index = VectorStoreIndex.from_documents([regulation_document])
        logger.info("Regulation index created successfully.")
    except Exception as e:
        logger.critical(f"Error creating regulation index: {e}. Exiting.")
        return

    # --- Process Contracts ---
    try:
        contract_files = [f for f in os.listdir(CONTRACT_FOLDER) if f.lower().endswith((".pdf", ".txt", ".docx"))]
        if not contract_files:
            logger.warning(f"No contract files found in {CONTRACT_FOLDER}. Exiting.")
            return
        logger.info(f"Found {len(contract_files)} contract(s) to process in {CONTRACT_FOLDER}.")
    except FileNotFoundError:
        logger.error(f"Contract folder not found: {CONTRACT_FOLDER}. Exiting.")
        return
    except Exception as e:
        logger.exception(f"Error listing contract files in {CONTRACT_FOLDER}: {e}. Exiting.")
        return

    # --- Analysis Loop for Each Contract ---
    for contract_file_name in contract_files:
        contract_file_path = os.path.join(CONTRACT_FOLDER, contract_file_name)
        logger.info(f"--- Processing contract: {contract_file_path} ---")
        base_report_name = os.path.splitext(contract_file_name)[0] + "_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") # Add timestamp

        try:
            contract_nodes = parse_contract(contract_file_path)
        except Exception as e:
            # Error already logged in parse_contract
            logger.error(f"Skipping contract {contract_file_name} due to parsing error.")
            continue # Skip to the next contract

        if not contract_nodes:
             logger.warning(f"No nodes parsed from contract {contract_file_name}. Skipping.")
             continue

        # --- Generate Prompts & Metadata ---
        tasks = []
        prompt_metadata_list = []
        logger.info(f"Generating prompts and async tasks for {len(contract_nodes)} contract node(s).")
        node_processing_errors = 0
        prompts_generated = 0
        for node in contract_nodes:
            try:
                contract_content = node.get_content()
                if not contract_content or contract_content.isspace():
                    logger.debug(f"Skipping empty node: {node.node_id}")
                    continue

                # Find relevant regulations (function now returns list[NodeWithScore])
                relevant_regs = find_relevant_regulations(node, regulation_index) # Error logged within function

                if not relevant_regs:
                     logger.debug(f"No relevant regulations found for node {node.node_id}. Skipping LLM call for this node.")
                     continue

                for reg_result in relevant_regs:
                    reg_node = reg_result.node
                    reg_content = reg_node.get_content()
                    reg_metadata = reg_node.metadata or {} # Ensure metadata exists

                    if not reg_content or reg_content.isspace():
                         logger.debug(f"Skipping empty regulation node: {reg_node.node_id}")
                         continue

                    # Create prompt using the updated function
                    prompt = create_violation_prompt(contract_content, reg_content, reg_metadata)
                    logger.debug(f"Generated prompt for C:{node.node_id[:8]}/R:{reg_node.node_id[:8]}")

                    # Create async task for LLM completion
                    tasks.append(Settings.llm.acomplete(prompt))
                    # Store metadata (include snippets for reporting)
                    prompt_metadata_list.append({
                        "contract_node_id": node.node_id,
                        "regulation_node_id": reg_node.node_id,
                        "contract_clause_snippet": contract_content[:300] + "...", # Slightly longer snippet
                        "regulation_excerpt_snippet": reg_content[:300] + "...", # Slightly longer snippet
                    })
                    prompts_generated += 1

            except Exception as e:
                 logger.exception(f"Error during prompt generation or retrieval for node {node.node_id}: {e}")
                 node_processing_errors += 1

        if node_processing_errors > 0:
            logger.warning(f"Encountered errors processing {node_processing_errors} node(s).")

        if not tasks:
            logger.warning(f"No valid prompts generated for contract {contract_file_name}. Skipping analysis.")
            continue # Skip to the next contract

        logger.info(f"Generated {prompts_generated} prompts for {len(tasks)} LLM tasks.")

        # --- Execute LLM Batch ---
        logger.info(f"Sending {len(tasks)} prompts to LLM concurrently via asyncio.gather...")
        all_violations = []
        batch_responses = []
        try:
            start_time = asyncio.get_event_loop().time()
            # Execute tasks concurrently
            batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = asyncio.get_event_loop().time()
            logger.info(f"Received {len(batch_responses)} responses/exceptions from LLM in {end_time - start_time:.2f} seconds.")

            # --- Process Responses ---
            all_violations = process_batch_violation_responses(batch_responses, prompt_metadata_list) # Errors logged within function

        except Exception as e:
            logger.exception(f"Critical error during asyncio.gather or batch processing for {contract_file_name}: {e}")
            # all_violations remains empty

        # --- Generate Reports ---
        logger.info(f"Generating reports for {contract_file_name}...")
        report_data = {
            "contract_name": contract_file_name,
            "contract_path": contract_file_path,
            "regulation_file": REGULATION_FILE,
            "analysis_timestamp": datetime.datetime.now().isoformat(),
            "total_prompts_sent": len(tasks),
            "successful_responses": sum(1 for r in batch_responses if not isinstance(r, Exception)),
            "failed_responses": sum(1 for r in batch_responses if isinstance(r, Exception)),
            "potential_issues_found": len(all_violations),
            "violations": all_violations, # Contains detailed violation dicts
        }

        # Define report paths
        json_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.json")
        txt_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.txt")
        pdf_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.pdf") # PDF Path

        # Generate all reports
        generate_report(report_data, json_report_path) # JSON
        generate_text_report(report_data, txt_report_path) # Text
        generate_pdf_report(report_data, pdf_report_path) # PDF (function logs errors internally)

    logger.info("--- Contract Compliance Analysis Complete ---")

# Use asyncio.run() to execute the async main function
if __name__ == "__main__":
    # Add note about resource module if needed (though it's just a warning)
    try:
        import resource
    except ImportError:
        logger.info("resource module not available on Windows. Usage statistics will not be available.")
    asyncio.run(main())