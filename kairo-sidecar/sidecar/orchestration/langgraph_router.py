"""
LangGraph Orchestration for Kairo Phantom.

Uses LangGraph StateGraph for multi-domain workflows.
Single-domain requests go to the existing router; multi-domain requests
go through LangGraph orchestration.

All nodes pass through security stack (PromptShield before, Sentinel after).
LangGraph is additive — it does NOT replace the existing router.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, TypedDict
from dataclasses import dataclass

log = logging.getLogger("kairo-sidecar.langgraph_router")

# ── State Definition ──────────────────────────────────────────────────────────


class WorkflowState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    input_text: str
    contract_text: str
    clause_list: List[Dict[str, Any]]
    slide_content: List[Dict[str, Any]]
    email_body: str
    summary: str
    metadata: Dict[str, Any]
    errors: List[str]
    node_history: List[str]


# ── Intent Gate ───────────────────────────────────────────────────────────────


@dataclass
class IntentClassification:
    """Result of intent classification."""

    is_multi_domain: bool
    domains: List[str]
    workflow: Optional[str] = None


def classify_intent(request: str) -> IntentClassification:
    """
    Classify a user request as single-domain or multi-domain.
    Single-domain → existing router.
    Multi-domain → LangGraph orchestrator.
    """
    request_lower = request.lower()
    domains = []

    # Detect domain keywords
    domain_keywords = {
        "legal": ["contract", "clause", "agreement", "legal", "liability", "termination", "cuad"],
        "pptx": ["presentation", "slides", "deck", "powerpoint", "slide"],
        "word": ["document", "word", "docx", "letter", "memo"],
        "excel": ["spreadsheet", "excel", "xlsx", "formula", "data", "table"],
        "pdf": ["pdf", "report", "invoice"],
        "email": ["email", "send", "mail", "compose"],
        "code": ["code", "function", "python", "rust", "javascript", "refactor"],
        "export": ["export", "epub", "html", "markdown", "latex", "json", "kami"],
        "memory": ["remember", "recall", "memory", "semantic"],
    }

    for domain, keywords in domain_keywords.items():
        if any(kw in request_lower for kw in keywords):
            domains.append(domain)

    # Multi-domain if 2+ domains detected
    is_multi = len(domains) >= 2

    # Detect specific workflows
    workflow = None
    if is_multi:
        if "legal" in domains and "pptx" in domains and "email" in domains:
            workflow = "contract_to_email"
        elif "legal" in domains and "pptx" in domains:
            workflow = "contract_to_slides"
        elif "pdf" in domains and "export" in domains:
            workflow = "pdf_to_export"
        elif "word" in domains and "export" in domains:
            workflow = "doc_to_export"

    return IntentClassification(
        is_multi_domain=is_multi,
        domains=domains,
        workflow=workflow,
    )


# ── Security Wrapper ──────────────────────────────────────────────────────────


def secure_node(node_name: str, node_fn):
    """Wrap a node function with PromptShield (before) and Sentinel (after)."""

    def wrapped(state: WorkflowState) -> WorkflowState:
        # Pre-security: scan input
        input_text = state.get("input_text", "")
        if input_text:
            try:
                from sidecar.safety.security_enhanced import scan_with_domain12

                is_safe, matched = scan_with_domain12(input_text)
                if not is_safe:
                    log.warning(
                        f"LangGraph node '{node_name}': input blocked by PromptShield — {matched}"
                    )
                    state["errors"] = state.get("errors", []) + [
                        f"Security: {node_name} input blocked"
                    ]
                    return state
            except ImportError:
                pass

        # Execute node
        log.info(f"LangGraph: executing node '{node_name}'")
        result = node_fn(state)

        # Post-security: scan output
        output_text = ""
        if isinstance(result, dict):
            output_text = (
                result.get("summary", "")
                or result.get("email_body", "")
                or str(result.get("clause_list", ""))
            )
        if output_text:
            try:
                from sidecar.safety.security_enhanced import RecursiveSentinel

                sentinel = RecursiveSentinel()
                if not sentinel.is_safe(output_text):
                    log.warning(f"LangGraph node '{node_name}': output flagged by Sentinel")
                    result["errors"] = result.get("errors", []) + [
                        f"Security: {node_name} output flagged"
                    ]
            except ImportError:
                pass

        # Track node history
        if isinstance(result, dict):
            result["node_history"] = result.get("node_history", []) + [node_name]

        return result

    return wrapped


# ── Domain Node Functions ─────────────────────────────────────────────────────


def node_parse_contract(state: WorkflowState) -> WorkflowState:
    """Parse a contract document — extract text and structure."""
    text = state.get("input_text", "")
    state["contract_text"] = text
    state["summary"] = f"Parsed contract: {len(text)} chars, {text.count(chr(10))} lines"
    log.info(f"parse_contract: {state['summary']}")
    return state


def node_extract_clauses(state: WorkflowState) -> WorkflowState:
    """Extract key clauses from contract text."""
    text = state.get("contract_text", "")
    clauses = []
    # Simple clause extraction (in production, uses CUAD from Domain 5)
    clause_types = ["termination", "liability", "payment", "confidentiality", "warranty"]
    for clause_type in clause_types:
        if clause_type in text.lower():
            clauses.append(
                {"type": clause_type, "found": True, "text": f"Clause about {clause_type}"}
            )
    state["clause_list"] = clauses
    log.info(f"extract_clauses: found {len(clauses)} clauses")
    return state


def node_generate_slides(state: WorkflowState) -> WorkflowState:
    """Generate slide content from extracted clauses."""
    clauses = state.get("clause_list", [])
    slides = []
    # Title slide
    slides.append(
        {"title": "Contract Analysis", "content": state.get("summary", "Contract Review")}
    )
    # One slide per clause
    for clause in clauses:
        slides.append({"title": clause["type"].title(), "content": clause["text"]})
    # Summary slide
    slides.append({"title": "Summary", "content": f"Found {len(clauses)} key clauses"})
    state["slide_content"] = slides
    log.info(f"generate_slides: created {len(slides)} slides")
    return state


def node_compose_email(state: WorkflowState) -> WorkflowState:
    """Compose an email with the analysis results."""
    slides = state.get("slide_content", [])
    clauses = state.get("clause_list", [])
    email = f"""Subject: Contract Analysis Report

Dear Team,

I've completed the contract analysis. Here are the key findings:

Key Clauses Found: {len(clauses)}
- {chr(10).join('- ' + c['type'] for c in clauses)}

Slides Generated: {len(slides)}

Please review the attached presentation for details.

Best regards,
Kairo Phantom"""
    state["email_body"] = email
    log.info(f"compose_email: {len(email)} chars")
    return state


def node_export_results(state: WorkflowState) -> WorkflowState:
    """Export results in the requested format."""
    state["summary"] = (
        f"Workflow complete. Clauses: {len(state.get('clause_list', []))}, Slides: {len(state.get('slide_content', []))}"
    )
    log.info(f"export_results: {state['summary']}")
    return state


# ── LangGraph Router ──────────────────────────────────────────────────────────


class LangGraphRouter:
    """
    Routes multi-domain requests through LangGraph StateGraph.
    Single-domain requests bypass this and go to the existing router.
    """

    def __init__(self) -> None:
        self._graph = None
        self._compiled = False

    def _build_graph(self):
        """Build the LangGraph StateGraph with domain nodes."""
        try:
            from langgraph.graph import StateGraph, END
        except ImportError:
            log.error("LangGraph not installed — multi-domain orchestration unavailable")
            return None

        # Define workflow graphs
        graph = StateGraph(WorkflowState)

        # Add nodes (wrapped with security)
        graph.add_node("parse_contract", secure_node("parse_contract", node_parse_contract))
        graph.add_node("extract_clauses", secure_node("extract_clauses", node_extract_clauses))
        graph.add_node("generate_slides", secure_node("generate_slides", node_generate_slides))
        graph.add_node("compose_email", secure_node("compose_email", node_compose_email))
        graph.add_node("export_results", secure_node("export_results", node_export_results))

        # Define edges (workflow order)
        graph.set_entry_point("parse_contract")
        graph.add_edge("parse_contract", "extract_clauses")
        graph.add_edge("extract_clauses", "generate_slides")
        graph.add_edge("generate_slides", "compose_email")
        graph.add_edge("compose_email", "export_results")
        graph.add_edge("export_results", END)

        return graph.compile()

    def execute(self, request: str, input_text: str) -> Dict[str, Any]:
        """
        Execute a multi-domain workflow.
        Returns the final state after all nodes have executed.
        """
        if self._graph is None:
            self._graph = self._build_graph()
            if self._graph is None:
                return {"error": "LangGraph not available", "results": None}

        initial_state: WorkflowState = {
            "input_text": input_text,
            "metadata": {"request": request},
            "errors": [],
            "node_history": [],
        }

        try:
            final_state = self._graph.invoke(initial_state)
            log.info(f"LangGraph workflow complete: {final_state.get('node_history', [])}")
            return {
                "ok": True,
                "results": final_state,
                "node_history": final_state.get("node_history", []),
                "errors": final_state.get("errors", []),
            }
        except Exception as e:
            log.error(f"LangGraph execution failed: {e}", exc_info=True)
            return {"ok": False, "error": str(e), "results": None}

    def route(self, request: str, input_text: str = "") -> Dict[str, Any]:
        """
        Main entry point: classify intent and route accordingly.
        Single-domain → return routing info (caller uses existing router).
        Multi-domain → execute LangGraph workflow.
        """
        intent = classify_intent(request)

        if not intent.is_multi_domain:
            return {
                "route": "existing_router",
                "domains": intent.domains,
                "reason": "Single-domain request — using existing router",
            }

        # Multi-domain: execute LangGraph
        result = self.execute(request, input_text)
        result["route"] = "langgraph"
        result["domains"] = intent.domains
        result["workflow"] = intent.workflow
        return result
