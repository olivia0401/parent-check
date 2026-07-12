"""
MCP server exposing Parent Check's scam-analysis tools over the Model Context
Protocol.

Any MCP client (Claude Desktop, an IDE, another agent) can now call the same
two tools the in-app Gemini agent uses - `check_phone_numbers` and
`query_knowledge_base` - with a published schema, input validation, and audit
logging. This reuses the exact production tool code in ai/tools.py rather than
reimplementing it, so the MCP surface can't drift from the app.

Run (stdio transport, e.g. for Claude Desktop):
    python mcp_server.py

Privacy: we log the length of the analysed text, never its contents - the same
principle the app follows for stored history.
"""
import logging

from mcp.server.fastmcp import FastMCP

from ai.tools import execute_check_phone, execute_query_rag

log = logging.getLogger("parent-check.mcp")

MAX_TEXT = 5000
VALID_LANGS = {"zh", "en"}

mcp = FastMCP("parent-check")


def _validate(text, lang):
    """Reject bad input at the MCP boundary before running any tool."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text exceeds {MAX_TEXT} characters")
    if lang not in VALID_LANGS:
        raise ValueError(f"lang must be one of {sorted(VALID_LANGS)}")


def _audit(tool, text, lang):
    """Audit log: tool name + input length + language, never the content."""
    log.info(
        "mcp tool call",
        extra={"path": tool, "method": "MCP", "status": 0,
               "request_id": f"len={len(text)},lang={lang}"},
    )


@mcp.tool()
def check_phone_numbers(text: str, lang: str = "en") -> dict:
    """Extract every phone number from a message and classify each one
    (international, premium-rate, mobile, official helpline, ...).

    Args:
        text: The full message text to scan.
        lang: "en" for UK-style classification, "zh" for China-style.
    """
    _validate(text, lang)
    _audit("check_phone_numbers", text, lang)
    return execute_check_phone(text, lang)


@mcp.tool()
def query_knowledge_base(text: str, lang: str = "en") -> dict:
    """Search the scam-case knowledge base for cases similar to a message,
    using vector similarity over the Parent Check corpus.

    Requires the database and GEMINI_API_KEY (for embeddings); returns an error
    object if the knowledge base isn't configured, so the client can degrade.

    Args:
        text: The message or key phrase to search for similar scams.
        lang: "en" or "zh" - selects the language-specific corpus.
    """
    _validate(text, lang)
    _audit("query_knowledge_base", text, lang)
    try:
        from ai.llm_client import LLMClient
        from ai.rag_engine import ScamRAGEngine

        llm = LLMClient()
        if not llm.available:
            return {"error": "knowledge base unavailable: GEMINI_API_KEY not set"}
        rag = ScamRAGEngine(llm, lang)
        return execute_query_rag(text, rag, lang)
    except Exception as e:
        return {"error": f"knowledge base lookup failed: {e}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()
