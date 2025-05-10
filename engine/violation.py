# engine/violation.py
import logging
import re # Import regex for parsing
from llama_index.core.schema import NodeWithScore
from llama_index.core.base.llms.types import CompletionResponse

# Configure logging for this module
logger = logging.getLogger(__name__)

def create_violation_prompt(contract_node_content: str, reg_node_content: str, reg_metadata: dict) -> str:
    """
    Creates a formatted prompt string for violation detection, asking for severity and reference.

    Args:
        contract_node_content (str): The text content of the contract node.
        reg_node_content (str): The text content of the relevant regulation node.
        reg_metadata (dict): Metadata from the regulation node (e.g., page number, filename).

    Returns:
        str: The formatted prompt string.
    """
    # Try to get a specific reference from metadata (adapt based on actual metadata keys)
    regulation_source_hint = reg_metadata.get('file_name', 'the regulation')
    page_label = reg_metadata.get('page_label')
    if page_label:
        regulation_source_hint += f", page {page_label}"

    # Location context added based on user profile
    # Current time: Sunday, April 27, 2025 at 2:26:25 PM GMT
    # Current location: Tema, Greater Accra Region, Ghana
    prompt = f"""
    You are a meticulous legal compliance analyst specializing in Ghanaian petroleum contracts under the Petroleum (Local Content and Local Participation) Regulations, 2013 (L.I. 2204), specifically focusing on operations relevant to Tema, Greater Accra Region.

    **Contract Clause:**
    ---
    {contract_node_content}
    ---

    **Relevant Regulation Excerpt (from {regulation_source_hint}):**
    ---
    {reg_node_content}
    ---

    **Task:**
    1.  Thoroughly analyze the Contract Clause **strictly** against the provided Regulation Excerpt.
    2.  Identify *every* instance where the clause fails to meet requirements, conflicts with, or is ambiguous regarding the excerpt.
    3.  For **each distinct issue** identified, provide the following details in the specified format:
        * **Issue:** Clearly describe the discrepancy (e.g., "The clause mandates X, but the regulation requires Y.", "The clause omits the requirement Z mentioned in the regulation.").
        * **Category:** Classify the issue as (Non-compliant Clause, Missing Obligation, Ambiguity).
        * **Regulation Ref:** State the specific section, paragraph, or number from the Regulation Excerpt that is relevant to this issue (e.g., "Regulation 17(a)", "Sub-regulation (3)"). If not explicitly numbered, describe its location (e.g., "Third paragraph").
        * **Severity:** Assess the potential impact of this specific issue and assign a severity level:
            * **High:** Significant risk (e.g., potential contract termination, major penalties, direct conflict with core regulatory principle).
            * **Medium:** Moderate risk (e.g., potential fines, operational hurdles, clear deviation from requirement but perhaps with lower impact).
            * **Low:** Minor risk (e.g., ambiguity needing clarification, minor deviation, potential procedural issue).
    4.  **Format:** Present each identified issue as a separate block, starting with "--- ISSUE START ---" and ending with "--- ISSUE END ---". Use the exact field names (Issue, Category, Regulation Ref, Severity).

    **Example Output Format:**

    --- ISSUE START ---
    Issue: The contract clause specifies quarterly reporting, while the regulation excerpt mandates an annual Local Content Performance Report.
    Category: Non-compliant Clause
    Regulation Ref: Regulation 34
    Severity: Medium
    --- ISSUE END ---

    --- ISSUE START ---
    Issue: The clause omits the requirement to maintain a bank account with an indigenous Ghanaian bank.
    Category: Missing Obligation
    Regulation Ref: Regulation 33
    Severity: High
    --- ISSUE END ---

    **Important:** If the contract clause fully complies with *this specific Regulation Excerpt* and has no ambiguities in relation to it, respond ONLY with the exact phrase: "No issues found." Do not add any explanation if no issues are found.
    """
    return prompt

def parse_llm_response(response_text: str, metadata: dict) -> list[dict]:
    """
    Parses the structured response from the LLM to extract violation details.

    Args:
        response_text (str): The text response from the LLM.
        metadata (dict): Metadata associated with the prompt (for context).

    Returns:
        list: A list of parsed violation dictionaries.
    """
    violations = []
    # Regex to find blocks and capture fields (case-insensitive keys, flexible whitespace)
    pattern = re.compile(
        r"---\s*ISSUE\s+START\s*---\s*"
        r"Issue:\s*(.*?)\s*"
        r"Category:\s*(.*?)\s*"
        r"Regulation\s+Ref:\s*(.*?)\s*"
        r"Severity:\s*(High|Medium|Low|N/A)\s*" # Expect specific values or N/A
        r"---\s*ISSUE\s+END\s*---",
        re.IGNORECASE | re.DOTALL # Ignore case for keys, DOTALL for multiline content
    )

    if "No issues found." in response_text:
        return []

    for match in pattern.finditer(response_text):
        description = match.group(1).strip()
        category = match.group(2).strip()
        reg_ref = match.group(3).strip()
        severity = match.group(4).strip().capitalize() # Capitalize High/Medium/Low

        violations.append({
            "description": description,
            "category": category,
            "regulation_ref": reg_ref if reg_ref else "N/A", # Default if empty
            "severity": severity if severity in ["High", "Medium", "Low"] else "Medium", # Default if invalid
            "type": "Potential Compliance Issue", # More professional type
            "contract_node_id": metadata.get("contract_node_id"),
            "regulation_node_id": metadata.get("reg_node_id"),
            "contract_snippet": metadata.get("contract_clause_snippet"),
            "regulation_snippet": metadata.get("regulation_excerpt_snippet"),
        })

    # Fallback if parsing fails but response is not "No issues found."
    if not violations and "No issues found." not in response_text:
         logger.warning(f"Could not parse potential violation details from LLM response for contract node {metadata.get('contract_node_id')}, reg node {metadata.get('reg_node_id')}. Storing raw response.")
         violations.append({
            "description": response_text, # Store raw response
            "category": "Uncategorized",
            "regulation_ref": "N/A",
            "severity": "Medium", # Default severity
            "type": "Potential Compliance Issue (Parsing Failed)",
            "contract_node_id": metadata.get("contract_node_id"),
            "regulation_node_id": metadata.get("reg_node_id"),
            "contract_snippet": metadata.get("contract_clause_snippet"),
            "regulation_snippet": metadata.get("regulation_excerpt_snippet"),
         })


    return violations


def process_batch_violation_responses(
    batch_responses: list[CompletionResponse | Exception], # Allow exceptions
    prompt_metadata: list[dict]
) -> list[dict]:
    """
    Processes the batch responses from the LLM to extract violations using structured parsing.

    Args:
        batch_responses (list[CompletionResponse | Exception]): List of responses/exceptions from llm.acomplete.
        prompt_metadata (list[dict]): List of metadata dicts corresponding to each prompt.

    Returns:
        list: A list of potential violations, including context from metadata.
    """
    all_violations = []
    successful_responses = 0
    failed_responses = 0

    logger.info(f"Processing {len(batch_responses)} LLM responses/exceptions...")
    for i, response in enumerate(batch_responses):
        metadata = prompt_metadata[i] # Get metadata regardless of success
        if isinstance(response, Exception):
            logger.error(f"LLM Task failed for contract node {metadata.get('contract_node_id')}, reg node {metadata.get('reg_node_id')}: {response}")
            failed_responses += 1
            continue # Skip processing for this failed task

        # Process successful response
        successful_responses += 1
        response_text = response.text.strip()
        logger.debug(f"Raw LLM response for C:{metadata.get('contract_node_id', 'N/A')[:8]}/R:{metadata.get('reg_node_id', 'N/A')[:8]}:\n{response_text[:200]}...") # Log snippet

        if response_text: # Check if response is not empty
            # Parse the potentially structured response
            parsed_violations = parse_llm_response(response_text, metadata)
            if parsed_violations:
                all_violations.extend(parsed_violations)
            elif "No issues found." not in response_text :
                 # Log if parsing failed but it wasn't a 'No issues found' response (already handled in parse_llm_response)
                 logger.warning(f"Non-empty response received but no structured issues parsed and not 'No issues found' for C:{metadata.get('contract_node_id', 'N/A')[:8]}/R:{metadata.get('reg_node_id', 'N/A')[:8]}.")
        else:
            logger.warning(f"Received empty response from LLM for C:{metadata.get('contract_node_id', 'N/A')[:8]}/R:{metadata.get('reg_node_id', 'N/A')[:8]}.")


    logger.info(f"Processed LLM results: {successful_responses} successful, {failed_responses} failed.")
    logger.info(f"Extracted {len(all_violations)} potential compliance issues.")
    return all_violations
