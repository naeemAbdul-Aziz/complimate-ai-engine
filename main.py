import os
from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
import chromadb
from PyPDF2 import PdfReader
from engine.parsing import parse_contract
from engine.retrieval import find_relevant_regulations
from engine.violation import detect_violations
from reporting.report_generator import generate_report, generate_text_report


# constants
REGULATION_FILE = "data/regulations/li_2204.pdf"
CONTRACT_FOLDER = "data/contracts"

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

def load_regulation(file_path):
    """Loads and preprocesses the regulation text from a PDF file.

    Args:
        file_path (str): Path to the regulation PDF file.

    Returns:
        str: The regulation text.
    """
    text = ""
    try:
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"Error reading regulation file: {e}")
        return ""

def main():
    """Main function to run the contract compliance analysis."""

    # Initialize LLM and Embedding Model
    Settings.llm = OpenAI(model="gpt-4", api_key=openai_api_key)
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-ada-002", api_key=openai_api_key)


    # Load Regulation
    regulation_text = load_regulation(REGULATION_FILE)

    # Create Llama Index for the regulation
    regulation_document = Document(text=regulation_text)
    regulation_index = VectorStoreIndex.from_documents([regulation_document])

    # Process all contracts in the contracts folder
    contract_folder = CONTRACT_FOLDER
    contract_files = [f for f in os.listdir(contract_folder) if f.lower().endswith((".pdf", ".txt", ".docx"))]

    for contract_file_name in contract_files:
        contract_file_path = os.path.join(contract_folder, contract_file_name)
        print(f"Processing contract: {contract_file_path}")

        contract_nodes = parse_contract(contract_file_path)

        if contract_nodes:
            all_violations = []
            for node in contract_nodes:
                relevant_regs = find_relevant_regulations(node, regulation_index)
                violations = detect_violations(node, relevant_regs, Settings.llm)
                all_violations.extend(violations)

            report_data = {
                "contract_name": contract_file_name,
                "violations": all_violations,
            }
            generate_report(report_data, f"reports/{os.path.splitext(contract_file_name)[0]}_report.json")
            generate_text_report(report_data, f"reports/{os.path.splitext(contract_file_name)[0]}_report.txt")
        else:
            print(f"Failed to process contract: {contract_file_path}")

if __name__ == "__main__":
    main()

# main.py
import os
import asyncio # Import asyncio
from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from PyPDF2 import PdfReader
from engine.parsing import parse_contract
from engine.retrieval import find_relevant_regulations
from engine.violation import create_violation_prompt, process_batch_violation_responses
# Assuming report generator exists and is synchronous
# If report generators are async, they need 'await' too.
from reporting.report_generator import generate_report, generate_text_report


# constants
REGULATION_FILE = "data/regulations/li_2204.pdf"
CONTRACT_FOLDER = "data/contracts"
REPORTS_FOLDER = "reports"

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

# Keep load_regulation synchronous as it's I/O bound
def load_regulation(file_path):
    """Loads and preprocesses the regulation text from a PDF file."""
    print(f"⏳ Loading regulation file: {file_path}")
    text = ""
    try:
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        print(f"✅ Regulation loaded ({len(text)} characters).")
        return text
    except FileNotFoundError:
        print(f"❌ Error: Regulation file not found at {file_path}")
        return ""
    except Exception as e:
        print(f"❌ Error reading regulation file: {e}")
        return ""

# Change main to be an async function
async def main():
    """Main async function to run the contract compliance analysis."""

    if not openai_api_key:
        print("❌ Error: OPENAI_API_KEY not found in environment variables.")
        return

    if not os.path.exists(REPORTS_FOLDER):
        os.makedirs(REPORTS_FOLDER)
        print(f"📂 Created reports directory: {REPORTS_FOLDER}")

    print("⚙️ Initializing LLM and Embedding models...")
    try:
        Settings.llm = OpenAI(model="gpt-4", api_key=openai_api_key)
        Settings.embed_model = OpenAIEmbedding(model="text-embedding-ada-002", api_key=openai_api_key)
        print("✅ Models initialized.")
    except Exception as e:
        print(f"❌ Error initializing OpenAI models: {e}")
        return

    regulation_text = load_regulation(REGULATION_FILE)
    if not regulation_text:
        return

    print("⚙️ Creating regulation index...")
    try:
        regulation_document = Document(text=regulation_text, doc_id=REGULATION_FILE)
        # Index creation is usually synchronous
        regulation_index = VectorStoreIndex.from_documents([regulation_document])
        print("✅ Regulation index created.")
    except Exception as e:
        print(f"❌ Error creating regulation index: {e}")
        return

    contract_folder = CONTRACT_FOLDER
    try:
        contract_files = [f for f in os.listdir(contract_folder) if f.lower().endswith((".pdf", ".txt", ".docx"))]
        if not contract_files:
            print(f"⚠️ No contract files found in {contract_folder}")
            return
    except FileNotFoundError:
        print(f"❌ Error: Contract folder not found at {contract_folder}")
        return
    except Exception as e:
        print(f"❌ Error listing contract files: {e}")
        return

    print(f"Found {len(contract_files)} contracts to process.")

    for contract_file_name in contract_files:
        contract_file_path = os.path.join(contract_folder, contract_file_name)
        print(f"\n--- Processing contract: {contract_file_path} ---")

        try:
            # Parsing is typically synchronous
            contract_nodes = parse_contract(contract_file_path)
        except Exception as e:
            print(f"❌ Failed to parse contract {contract_file_name}: {e}")
            continue

        if contract_nodes:
            tasks = []
            prompt_metadata_list = [] # Keep track of metadata in order

            print(f"⚙️ Generating prompts and async tasks for {len(contract_nodes)} contract nodes...")
            node_processing_errors = 0
            for node in contract_nodes:
                try:
                    contract_content = node.get_content()
                    if not contract_content or contract_content.isspace():
                        # print(f"⚠️ Skipping empty node: {node.node_id}") # Reduced verbosity
                        continue

                    # Retrieval can often be synchronous unless specifically using async retrievers
                    relevant_regs = find_relevant_regulations(node, regulation_index)

                    for reg_result in relevant_regs:
                        reg_node = reg_result.node
                        reg_content = reg_node.get_content()
                        if not reg_content or reg_content.isspace():
                            # print(f"⚠️ Skipping empty regulation node: {reg_node.node_id}") # Reduced verbosity
                             continue

                        prompt = create_violation_prompt(contract_content, reg_content)
                        # Create an async task for each prompt completion
                        tasks.append(Settings.llm.acomplete(prompt))
                        # Store metadata in the same order as tasks
                        prompt_metadata_list.append({
                            "contract_node_id": node.node_id,
                            "regulation_node_id": reg_node.node_id,
                            "contract_clause_snippet": contract_content[:200] + "...",
                            "regulation_excerpt_snippet": reg_content[:200] + "...",
                        })
                except Exception as e:
                     print(f"❌ Error during prompt generation/retrieval for node {node.node_id}: {e}")
                     node_processing_errors += 1
                     # Decide if we should stop the whole contract or just skip this node

            if node_processing_errors > 0:
                print(f"⚠️ Encountered errors processing {node_processing_errors} nodes.")

            if not tasks:
                print("⚠️ No valid prompts generated for this contract.")
                continue # Skip to the next contract

            print(f"✅ Generated {len(tasks)} prompts.")
            print(f"⏳ Sending {len(tasks)} prompts to LLM concurrently via asyncio.gather (this may still take time)...")

            all_violations = []
            try:
                # Perform the completions concurrently
                # Note: This sends requests concurrently, but actual speed depends on API rate limits and server load.
                batch_responses = await asyncio.gather(*tasks, return_exceptions=True)
                print(f"✅ Received {len(batch_responses)} responses (or exceptions) from LLM.")

                # Check for exceptions returned by gather
                processed_responses = []
                processed_metadata = []
                for i, response in enumerate(batch_responses):
                    if isinstance(response, Exception):
                        print(f"❌ Error in LLM response for prompt index {i}: {response}")
                        # Optionally log the failed prompt/metadata: print(f"Failed metadata: {prompt_metadata_list[i]}")
                    else:
                        # Only process valid responses
                        processed_responses.append(response)
                        processed_metadata.append(prompt_metadata_list[i])

                # Process the successful batch responses
                all_violations = process_batch_violation_responses(processed_responses, processed_metadata)

            except Exception as e:
                # Catch errors during asyncio.gather itself or subsequent processing
                print(f"❌ Error during asyncio.gather or batch processing: {e}")
                # all_violations remains empty or partially filled depending on where error occurred

            # Generate reports (synchronously for now)
            print("⚙️ Generating reports...")
            report_data = {
                "contract_name": contract_file_name,
                "contract_path": contract_file_path,
                "regulation_file": REGULATION_FILE,
                "total_prompts_sent": len(tasks),
                "successful_responses": len(processed_responses) if 'processed_responses' in locals() else 0,
                "potential_violations_found": len(all_violations),
                "violations": all_violations,
            }
            base_report_name = os.path.splitext(contract_file_name)[0]
            json_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.json")
            txt_report_path = os.path.join(REPORTS_FOLDER, f"{base_report_name}_report.txt")

            try:
                # Assuming these report functions are synchronous
                generate_report(report_data, json_report_path)
                print(f"✅ JSON report generated: {json_report_path}")
                generate_text_report(report_data, txt_report_path)
                print(f"✅ Text report generated: {txt_report_path}")
            except NameError:
                 print("⚠️ Reporting functions (generate_report, generate_text_report) not found. Skipping report generation.")
            except Exception as e:
                 print(f"❌ Error generating reports for {contract_file_name}: {e}")

        else:
            print(f"ℹ️ No nodes found after parsing contract: {contract_file_path}")

    print("\n--- Contract processing complete. ---")

# Use asyncio.run() to execute the async main function
if __name__ == "__main__":
    asyncio.run(main())