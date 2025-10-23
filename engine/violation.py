# engine/violation.py
import logging
import re # Import regex for parsing
from llama_index.core.schema import NodeWithScore
from llama_index.core.base.llms.types import CompletionResponse

# Configure logging for this module
logger = logging.getLogger(__name__)

# --- Prompt scrubbing (PII/sensitive data minimization) ---
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?)?\d{3}[\s-]?\d{4}\b")
_ACCOUNT_RE = re.compile(r"\b(?:ACCT|ACCOUNT|IBAN|SWIFT|BANK)[:\s]*[A-Z0-9\-]{6,}\b", re.IGNORECASE)
_ID_RE = re.compile(r"\b(?:TIN|SSN|NIN|ID|PASSPORT)[:\s]*[A-Z0-9\-]{4,}\b", re.IGNORECASE)
_CURRENCY_RE = re.compile(r"\b(?:USD|GHS|GH¢|US\$|\$|€|£)\s?\d{2,}(?:[,\.]\d{3})*(?:\.\d+)?\b")

def scrub_for_prompt(text: str, level: str = "medium") -> str:
    """Scrub PII/sensitive tokens before sending to LLM.

    level: light|medium|strict controls aggressiveness.
    """
    if not text:
        return text
    s = text
    # Always remove emails and obvious phones
    s = _EMAIL_RE.sub("[REDACTED_EMAIL]", s)
    s = _PHONE_RE.sub("[REDACTED_PHONE]", s)
    # Medium: remove account IDs and government IDs
    s = _ACCOUNT_RE.sub("[REDACTED_ACCOUNT]", s)
    s = _ID_RE.sub("[REDACTED_ID]", s)
    # Monetary amounts — only in strict mode or when likely not essential
    if level == "strict":
        s = _CURRENCY_RE.sub("[REDACTED_AMOUNT]", s)
    # Trim length to a safe upper bound to avoid over-sharing
    MAX_LEN = 2000
    if len(s) > MAX_LEN:
        s = s[:MAX_LEN] + "..."
    return s

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
    # Scrub inputs prior to prompt construction (zero-trust prompting)
    try:
        from config.settings import settings as app_settings  # local to avoid import cycles
        scrub_level = getattr(app_settings, "PROMPT_SCRUB_LEVEL", "medium")
    except Exception:
        scrub_level = "medium"
    contract_node_content = scrub_for_prompt(contract_node_content, scrub_level)
    reg_node_content = scrub_for_prompt(reg_node_content, scrub_level)

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

    **Important:**
    1.  You **MUST** respond using the "--- ISSUE START ---" / "--- ISSUE END ---" format.
    2.  If the clause **FULLY COMPLIES** with this specific excerpt, you **MUST** provide one block as follows:
    
    --- ISSUE START ---
    Issue: The clause is fully compliant with this regulation excerpt.
    Category: Compliant
    Regulation Ref: N/A
    Severity: N/A
    --- ISSUE END ---
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
    # UPDATED: Allow "Compliant" in Category and expanded Severity match
    pattern = re.compile(
        r"---\s*ISSUE\s+START\s*---\s*"
        r"Issue:\s*(.*?)\s*"
        r"Category:\s*(.*?)\s*"
        r"Regulation\s+Ref:\s*(.*?)\s*"
        r"Severity:\s*(High|Medium|Low|N/A)\s*" # Allow N/A
        r"---\s*ISSUE\s+END\s*---",
        re.IGNORECASE | re.DOTALL # Ignore case for keys, DOTALL for multiline content
    )

    # Handle the old "No issues found" just in case the model reverts
    if "No issues found." in response_text and not pattern.search(response_text):
        return []

    for match in pattern.finditer(response_text):
        description = match.group(1).strip()
        category = match.group(2).strip()
        reg_ref = match.group(3).strip()
        severity = match.group(4).strip().capitalize() # Capitalize High/Medium/Low/N/A

        # ADDED: Skip "Compliant" blocks
        if category.lower() == "compliant":
            continue

        violations.append({
            "description": description,
            "category": category,
            "regulation_ref": reg_ref if reg_ref else "N/A", # Default if empty
            "severity": severity if severity in ["High", "Medium", "Low"] else "Medium", # Default if invalid
            "type": "Potential Compliance Issue", # More professional type
            "contract_node_id": metadata.get("contract_node_id"),
            "regulation_node_id": metadata.get("regulation_node_id"),
            "contract_snippet": metadata.get("contract_clause_snippet"),
            "regulation_snippet": metadata.get("regulation_excerpt_snippet"),
        })

    # Fallback if parsing fails and no "Compliant" block was found
    if not violations and "Compliant" not in response_text and "No issues found." not in response_text:
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
            elif "No issues found." not in response_text and "Compliant" not in response_text:
                 # Log if parsing failed but it wasn't a 'No issues' or 'Compliant' response
                 logger.warning(f"Non-empty response received but no structured issues parsed and not 'No issues found' or 'Compliant' for C:{metadata.get('contract_node_id', 'N/A')[:8]}/R:{metadata.get('reg_node_id', 'N/A')[:8]}.")
        else:
            logger.warning(f"Received empty response from LLM for C:{metadata.get('contract_node_id', 'N/A')[:8]}/R:{metadata.get('reg_node_id', 'N/A')[:8]}.")


    logger.info(f"Processed LLM results: {successful_responses} successful, {failed_responses} failed.")
    logger.info(f"Extracted {len(all_violations)} potential compliance issues.")
    return all_violations