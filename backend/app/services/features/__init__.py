"""Interactive AI features built on top of the core document + LLM services:

citations      - parse [S1: Page 3] markers and resolve them to document sections
structured     - shared "prompt -> schema-constrained JSON -> Pydantic" helper
verify         - fact-check an answer claim by claim against the selected sources
study          - interactive quiz generation and AI grading of free-text answers
data_query     - natural language -> query plan -> deterministic local execution on tables
privacy_guard  - personal-data detection (regex + AI) and reviewed redaction
"""
