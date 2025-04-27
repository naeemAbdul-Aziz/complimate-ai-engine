from llama_index.llms.openai import OpenAI

def detect_violations(contract_node, relevant_regulations, llm: OpenAI):
    """
    Detects potential violations by comparing a contract node with relevant regulations using GPT-4.

    Args:
        contract_node (llama_index.core.Node): A node from the contract.
        relevant_regulations (list): A list of retrieved regulation nodes.
        llm (OpenAI): The OpenAI language model.

    Returns:
        list: A list of potential violations.
    """
    print("🔍 Analyzing contract clause for potential violations...")

    violations = []

    for reg_node in relevant_regulations:
        prompt = f"""
        You are a compliance analyst for petroleum contracts.

        Given the following contract clause:
        ---
        {contract_node.get_content()}
        ---

        And the following regulation excerpt:
        ---
        {reg_node.get_content()}
        ---

        Task:
        - Identify any missing obligations, non-compliant clauses, or ambiguities.
        - Categorize each issue as (Missing Term, Non-compliant Clause, Ambiguity).
        - Format your answer as a bullet-point list.

        If no issues are found, simply respond: "No issues found."
        """

        print("Prompting GPT-4 for analysis...")
        response = llm.complete(prompt)

        if response.text and "No issues found." not in response.text:
            violations.append({
                "type": "GPT-4 Analysis",
                "description": response.text.strip(),
                "contract_snippet": contract_node.get_content()[:200] + "...",
                "regulation_snippet": reg_node.get_content()[:200] + "...",
            })

    return violations
