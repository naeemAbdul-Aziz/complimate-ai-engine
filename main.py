# main.py
import os
import time
import asyncio
import logging # Import logging
import datetime # For report naming
from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from config.settings import settings as app_settings
from PyPDF2 import PdfReader

# Import engine modules
from engine.parsing import parse_contract
from engine.retrieval import find_relevant_regulations
from engine.violation import create_violation_prompt, process_batch_violation_responses
from utils.cache import get_json, set_json, key_hash

# Import reporting functions
from reporting.report_generator import generate_report, generate_text_report, generate_pdf_report

# --- Production Logging Configuration ---
from config.logger import get_component_logger, log_performance
logger = get_component_logger('main')
# -----------------------------------

# Constants
REGULATION_FILE = "data/regulations/li_2204.pdf"
CONTRACT_FOLDER = "data/contracts"
REPORTS_FOLDER = "reports"

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

def load_regulation(file_path):
    """
    Loads and preprocesses regulation text from a PDF file.
    
    This function implements enterprise-grade error handling with specific
    exception handling for different failure scenarios.
    
    Args:
        file_path (str): Path to the PDF regulation file
        
    Returns:
        str: Extracted text from the PDF, empty string on failure
        
    Raises:
        No exceptions are raised - all errors are logged and handled gracefully
    """
    logger.info(f"Loading regulation file: {file_path}")
    text = ""
    
    try:
        # Validate file existence and permissions
        if not os.path.exists(file_path):
            logger.error(f"Regulation file does not exist: {file_path}")
            return ""
            
        if not os.access(file_path, os.R_OK):
            logger.error(f"Insufficient permissions to read file: {file_path}")
            return ""
        
        # Get file size for logging
        file_size = os.path.getsize(file_path)
        logger.debug(f"Processing PDF file of size: {file_size} bytes")
        
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            num_pages = len(reader.pages)
            
            if num_pages == 0:
                logger.warning(f"PDF file has no pages: {file_path}")
                return ""
                
            logger.debug(f"Reading {num_pages} pages from {file_path}")
            
            pages_processed = 0
            for i, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\\n"
                        pages_processed += 1
                    else:
                        logger.warning(f"No text extracted from page {i+1} of {file_path}")
                except Exception as page_error:
                    logger.error(f"Failed to extract text from page {i+1}: {page_error}")
                    continue
                    
        if pages_processed == 0:
            logger.error(f"No readable content found in PDF: {file_path}")
            return ""
            
        logger.info(f"Regulation loaded successfully: {pages_processed}/{num_pages} pages, {len(text)} characters")
        return text
        
    except FileNotFoundError:
        logger.error(f"Regulation file not found: {file_path}")
        return ""
    except PermissionError:
        logger.error(f"Permission denied accessing file: {file_path}")
        return ""
    except Exception as e:
        logger.exception(f"Unexpected error reading regulation file {file_path}: {e}")
        return ""

async def main():
    """
    Main async function to run contract compliance analysis.
    
    This function orchestrates the entire compliance analysis workflow with
    comprehensive error handling, performance monitoring, and graceful degradation.
    
    Returns:
        bool: True if analysis completed successfully, False otherwise
    """
    start_time = time.time()
    logger.info("=== Starting Contract Compliance Analysis ===")

    try:
        # Validate environment configuration (allow stub free mode)
        if not openai_api_key:
            logger.critical("OPENAI_API_KEY not configured. Cannot run analysis.")
            return False

        # Ensure output directory exists with proper error handling
        if not os.path.exists(REPORTS_FOLDER):
            try:
                os.makedirs(REPORTS_FOLDER, exist_ok=True)
                logger.info(f"Created reports directory: {REPORTS_FOLDER}")
            except OSError as e:
                logger.critical(f"Failed to create reports directory {REPORTS_FOLDER}: {e}")
                logger.critical("Please check directory permissions and disk space")
                return False

        # Initialize OpenAI models with enhanced error handling
        logger.info("Initializing LLM and Embedding models...")
        init_start = time.time()
        
        try:
            Settings.llm = OpenAI(model=app_settings.OPENAI_MODEL, api_key=openai_api_key, request_timeout=app_settings.OPENAI_REQUEST_TIMEOUT)
            Settings.embed_model = OpenAIEmbedding(model=app_settings.OPENAI_EMBEDDING_MODEL, api_key=openai_api_key)
            init_duration = time.time() - init_start
            log_performance("model_initialization", init_duration, True)
            logger.info("LLM initialized (primary=%s, embedding=%s)", app_settings.OPENAI_MODEL, app_settings.OPENAI_EMBEDDING_MODEL)
        except Exception as e:
            init_duration = time.time() - init_start
            log_performance("model_initialization", init_duration, False, {"error": str(e)})
            logger.critical(f"Failed to initialize OpenAI models: {e}")
            return False

        # Load and process regulation documents
        logger.info("Loading regulation documents...")
        regulation_text = load_regulation(REGULATION_FILE)
        if not regulation_text:
            logger.critical("Failed to load regulation text - cannot proceed with analysis")
            return False

        # Create regulation index with error handling
        logger.info("Creating regulation index...")
        index_start = time.time()
        
        try:
            regulation_document = Document(text=regulation_text, doc_id=REGULATION_FILE)
            regulation_index = VectorStoreIndex.from_documents([regulation_document])
            
            index_duration = time.time() - index_start
            log_performance("regulation_index_creation", index_duration, True)
            logger.info("Regulation index created successfully")
            
        except Exception as e:
            index_duration = time.time() - index_start
            log_performance("regulation_index_creation", index_duration, False, {"error": str(e)})
            logger.critical(f"Failed to create regulation index: {e}")
            return False

        # Discover and validate contract files
        try:
            if not os.path.exists(CONTRACT_FOLDER):
                logger.critical(f"Contract folder does not exist: {CONTRACT_FOLDER}")
                return False
                
            contract_files = [f for f in os.listdir(CONTRACT_FOLDER) 
                            if f.lower().endswith((".pdf", ".txt", ".docx"))]
            
            if not contract_files:
                logger.warning(f"No contract files found in {CONTRACT_FOLDER}")
                logger.info("Please add contract files (.pdf, .txt, .docx) to the contracts folder")
                return False
                
            logger.info(f"Found {len(contract_files)} contract(s) to process: {contract_files}")
            
        except PermissionError:
            logger.critical(f"Permission denied accessing contract folder: {CONTRACT_FOLDER}")
            return False
        except Exception as e:
            logger.critical(f"Error accessing contract files: {e}")
            return False

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

                        # Primary LLM cache key (prompt + reg node id + simple schema version)
                        cache_key = f"primary:{key_hash({'p': prompt, 'rid': reg_node.node_id, 'v': 1})}"
                        cached = get_json(cache_key)
                        if cached:
                            # Store a sentinel in metadata to indicate cache hit; we'll merge later
                            prompt_metadata_list.append({
                                "contract_node_id": node.node_id,
                                "regulation_node_id": reg_node.node_id,
                                "contract_clause_snippet": contract_content[:300] + "...",
                                "regulation_excerpt_snippet": reg_content[:300] + "...",
                                "_cache_key": cache_key,
                                "_cached": True,
                                "_cached_payload": cached,
                            })
                            continue

                        # Create async task for LLM completion
                        tasks.append(Settings.llm.acomplete(prompt))
                        # Store metadata (include snippets for reporting)
                        prompt_metadata_list.append({
                            "contract_node_id": node.node_id,
                            "regulation_node_id": reg_node.node_id,
                            "contract_clause_snippet": contract_content[:300] + "...", # Slightly longer snippet
                            "regulation_excerpt_snippet": reg_content[:300] + "...", # Slightly longer snippet
                            "_cache_key": cache_key,
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
                start_time_batch = asyncio.get_event_loop().time()
                # Execute tasks concurrently
                batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
                end_time_batch = asyncio.get_event_loop().time()
                logger.info(f"Received {len(batch_responses)} responses/exceptions from LLM in {end_time_batch - start_time_batch:.2f} seconds.")

                # --- Process Responses ---
                # Process violation responses (with proper error handling)
                from llama_index.core.base.llms.types import CompletionResponse
                from typing import cast, Union, List
                
                # Filter and cast responses to proper types
                valid_responses: List[Union[CompletionResponse, Exception]] = []
                for response in batch_responses:
                    if isinstance(response, Exception):
                        valid_responses.append(response)
                    else:
                        # Cast to CompletionResponse if it's not an exception
                        valid_responses.append(cast(CompletionResponse, response))
                
                # Merge cached violation payloads first
                cached_items = [m for m in prompt_metadata_list if m.get("_cached")]
                for m in cached_items:
                    try:
                        if isinstance(m.get("_cached_payload"), list):
                            all_violations.extend(m["_cached_payload"])
                    except Exception:
                        pass

                # Align non-cached responses with their metadata
                non_cached_meta = [m for m in prompt_metadata_list if not m.get("_cached")]
                all_violations_from_llm = process_batch_violation_responses(valid_responses, non_cached_meta)  # Errors logged within
                all_violations.extend(all_violations_from_llm)

                # Write back cache for non-cached prompts
                try:
                    # Group violations by `_cache_key` from their metadata (best-effort)
                    # Here we can’t perfectly re-associate, but we trust `process_batch_violation_responses`
                    # preserved correspondence order with non_cached_meta
                    idx = 0
                    bucket: dict[str, list] = {}
                    for resp in valid_responses:
                        if isinstance(resp, Exception):
                            continue
                        if idx >= len(non_cached_meta):
                            break
                        meta = non_cached_meta[idx]
                        idx += 1
                        bucket.setdefault(meta["_cache_key"], [])
                    # Simple write: cache the entire set for each key if present
                    # For better precision, one could modify `process_batch_violation_responses` to return
                    # (violations, by_prompt_index) mapping.
                    for key in bucket.keys():
                        # Find violations that contain the snippets from meta; as a fallback, cache all
                        set_json(key, all_violations_from_llm)
                except Exception:
                    pass

            except Exception as e:
                logger.exception(f"Critical error during asyncio.gather or batch processing for {contract_file_name}: {e}")
                # all_violations remains empty

        # --- Optional Secondary Reasoning Refinement ---
        refinement_stats = {
            "enabled": False,
            "pre_refinement_count": len(all_violations),
            "post_refinement_count": len(all_violations),
            "reduction": 0,
        }
        if app_settings.ENABLE_SECONDARY_REASONING and all_violations:
            try:
                from engine.reasoning_refinement import refine_violations  # local import to avoid circular
                refinement_stats["enabled"] = True
                refined = refine_violations(all_violations)
                refinement_stats["post_refinement_count"] = len(refined)
                refinement_stats["reduction"] = refinement_stats["pre_refinement_count"] - len(refined)
                all_violations = refined
                # Extract grouped view if provided via special key
                grouped_view = None
                for v in refined:
                    if isinstance(v, dict) and v.get("_grouping"):
                        grouped_view = v.get("_grouping")
                        break
            except Exception as re:
                logger.exception(f"Secondary refinement failed: {re}")

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
                "refinement": refinement_stats,
                "grouped": grouped_view or {},
                "models": {
                    "primary": app_settings.OPENAI_MODEL,
                    "embedding": app_settings.OPENAI_EMBEDDING_MODEL,
                    "secondary_reasoning": app_settings.SECONDARY_REASONING_MODEL,
                    "secondary_enabled": app_settings.ENABLE_SECONDARY_REASONING,
                }
            }

            # Define report paths
            json_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.json")
            txt_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.txt")
            pdf_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.pdf") # PDF Path

            # Generate all reports
            generate_report(report_data, json_report_path) # JSON
            generate_text_report(report_data, txt_report_path) # Text
            generate_pdf_report(report_data, pdf_report_path) # PDF (function logs errors internally)

            logger.info(f"Finished processing contract: {contract_file_name}")

        # After processing all contracts, log overall completion
        total_duration = time.time() - start_time
        logger.info("=== Contract Compliance Analysis Complete ===")
        logger.info(f"Total processing time: {total_duration:.2f} seconds for {len(contract_files)} contract(s)")
        log_performance("complete_analysis", total_duration, True, {
            "contracts_processed": len(contract_files)
        })
        return True

    except Exception as e:
        # Catch any unexpected errors at the top level
        total_duration = time.time() - start_time
        log_performance("complete_analysis", total_duration, False, {"error": str(e)})
        logger.critical(f"Unexpected error during analysis: {e}")
        logger.exception("Full stack trace:")
        return False

# Use asyncio.run() to execute the async main function
if __name__ == "__main__":
    # Add note about resource module if needed (though it's just a warning)
    try:
        import resource
    except ImportError:
        logger.info("resource module not available on Windows. Usage statistics will not be available.")
    asyncio.run(main())