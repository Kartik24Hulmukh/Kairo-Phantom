"""
Legal Citation Graph — Build and query cross-document clause reference networks.

Uses networkx to construct a directed graph (DiGraph) where:
  - Nodes represent contract documents
  - Edges represent clause-level cross-references between documents
    (e.g. "this contract references Section 3 of the Master Agreement")

The graph is JSON-serializable for persistence and API responses.

Usage
-----
    from sidecar.parsers.legal_citation_graph import CitationGraph

    graph = CitationGraph()
    graph.add_document("NDA_v1.docx", text=nda_text)
    graph.add_document("Master_Services_Agreement.docx", text=msa_text)
    graph.add_citation("NDA_v1.docx", "Master_Services_Agreement.docx",
                       section="Section 5", clause_type="Confidentiality")
    graph.add_document("SOW_2024.docx", text=sow_text)
    graph.add_citation("SOW_2024.docx", "Master_Services_Agreement.docx",
                       section="Section 3", clause_type="Statement of Work")

    # Query: which documents reference Section 5 of the NDA?
    refs = graph.find_references_to("NDA_v1.docx", section="Section 5")
"""

from __future__ import annotations

import json
import logging
import re

import networkx as nx

log = logging.getLogger("kairo-sidecar.citation_graph")


class CitationGraph:
    """
    Directed graph of cross-document legal citations.

    Nodes are document names (str).  Edges carry metadata:
      - section:       str (e.g. "Section 5")
      - clause_type:   str (e.g. "Confidentiality")
      - reference_text: str (the sentence containing the citation)
      - confidence:    float
    """

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()

    # -- Node management ---------------------------------------------------

    def add_document(
        self,
        name: str,
        text: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Add a document node to the graph."""
        self.graph.add_node(name, text=text or "", metadata=metadata or {})

    def remove_document(self, name: str) -> None:
        """Remove a document and all its edges."""
        if name in self.graph:
            self.graph.remove_node(name)

    # -- Edge management ---------------------------------------------------

    def add_citation(
        self,
        source_doc: str,
        target_doc: str,
        section: str = "",
        clause_type: str = "",
        reference_text: str = "",
        confidence: float = 0.80,
    ) -> None:
        """
        Add a directed citation edge: source_doc → target_doc.

        This means source_doc references a section/clause in target_doc.
        """
        if source_doc not in self.graph:
            self.add_document(source_doc)
        if target_doc not in self.graph:
            self.add_document(target_doc)

        self.graph.add_edge(
            source_doc,
            target_doc,
            section=section,
            clause_type=clause_type,
            reference_text=reference_text,
            confidence=confidence,
        )

    # -- Auto-detection of citations from text -----------------------------

    def auto_detect_citations(
        self,
        source_doc: str,
        source_text: str,
        known_documents: list[str],
    ) -> list[dict]:
        """
        Scan source_text for references to known documents and auto-create edges.

        Detects patterns like:
          - "Section 5 of the Master Agreement"
          - "pursuant to Section 3 of the NDA"
          - "as defined in Article 2 of the Service Agreement"
          - "in accordance with [Document Name]"

        Returns list of detected citations as dicts.
        """
        if source_doc not in self.graph:
            self.add_document(source_doc, text=source_text)

        detected: list[dict] = []

        for target_doc in known_documents:
            if target_doc == source_doc:
                continue

            # Build search patterns from the target document name
            # Extract key words from the document name for fuzzy matching
            doc_base = re.sub(r"\.(docx?|pdf|txt)$", "", target_doc, flags=re.IGNORECASE)
            doc_words = [w for w in re.split(r"[_\-\s]+", doc_base) if len(w) > 2]

            # Pattern 1: "Section X of [document name/words]"
            for word in doc_words:
                pattern = rf"(?:Section|Article|Clause|Paragraph)\s+(\d+[.\d]*)\s+(?:of|in|under)\s+(?:the\s+)?\S*{re.escape(word)}\S*"
                for m in re.finditer(pattern, source_text, re.IGNORECASE):
                    section = f"Section {m.group(1)}"
                    ref_text = source_text[max(0, m.start() - 50) : m.end() + 50].strip()
                    self.add_citation(
                        source_doc,
                        target_doc,
                        section=section,
                        reference_text=ref_text,
                        confidence=0.85,
                    )
                    detected.append(
                        {
                            "source": source_doc,
                            "target": target_doc,
                            "section": section,
                            "reference_text": ref_text,
                            "confidence": 0.85,
                        }
                    )

            # Pattern 2: "[document name], Section X"
            for word in doc_words:
                pattern2 = (
                    rf"{re.escape(word)}\S*(?:\.docx?)?\s*,?\s*(?:Section|Article)\s+(\d+[.\d]*)"
                )
                for m in re.finditer(pattern2, source_text, re.IGNORECASE):
                    section = f"Section {m.group(1)}"
                    ref_text = source_text[max(0, m.start() - 50) : m.end() + 50].strip()
                    self.add_citation(
                        source_doc,
                        target_doc,
                        section=section,
                        reference_text=ref_text,
                        confidence=0.80,
                    )
                    detected.append(
                        {
                            "source": source_doc,
                            "target": target_doc,
                            "section": section,
                            "reference_text": ref_text,
                            "confidence": 0.80,
                        }
                    )

            # Pattern 3: "pursuant to [document name]" / "in accordance with [document name]"
            for word in doc_words:
                pattern3 = rf"(?:pursuant\s+to|in\s+accordance\s+with|as\s+defined\s+in|under)\s+(?:the\s+)?\S*{re.escape(word)}\S*"
                for m in re.finditer(pattern3, source_text, re.IGNORECASE):
                    ref_text = source_text[max(0, m.start() - 30) : m.end() + 80].strip()
                    self.add_citation(
                        source_doc,
                        target_doc,
                        section="",
                        reference_text=ref_text,
                        confidence=0.70,
                    )
                    detected.append(
                        {
                            "source": source_doc,
                            "target": target_doc,
                            "section": "",
                            "reference_text": ref_text,
                            "confidence": 0.70,
                        }
                    )

        log.info("auto_detect_citations: found %d citations from %s", len(detected), source_doc)
        return detected

    # -- Query operations --------------------------------------------------

    def find_references_to(
        self,
        target_doc: str,
        section: str | None = None,
    ) -> list[dict]:
        """
        Find all documents that reference the given target document.

        If section is provided, filter to only citations referencing that section.
        Returns list of citation dicts.
        """
        results: list[dict] = []
        for source, target, data in self.graph.in_edges(target_doc, data=True):
            if section and data.get("section", "").lower() != section.lower():
                continue
            results.append(
                {
                    "source_doc": source,
                    "target_doc": target,
                    "section": data.get("section", ""),
                    "clause_type": data.get("clause_type", ""),
                    "reference_text": data.get("reference_text", ""),
                    "confidence": data.get("confidence", 0.0),
                }
            )
        return results

    def find_references_from(self, source_doc: str) -> list[dict]:
        """Find all documents that the given source document references."""
        results: list[dict] = []
        for source, target, data in self.graph.out_edges(source_doc, data=True):
            results.append(
                {
                    "source_doc": source,
                    "target_doc": target,
                    "section": data.get("section", ""),
                    "clause_type": data.get("clause_type", ""),
                    "reference_text": data.get("reference_text", ""),
                    "confidence": data.get("confidence", 0.0),
                }
            )
        return results

    def get_all_citations(self) -> list[dict]:
        """Return all citation edges in the graph."""
        results: list[dict] = []
        for source, target, data in self.graph.edges(data=True):
            results.append(
                {
                    "source_doc": source,
                    "target_doc": target,
                    "section": data.get("section", ""),
                    "clause_type": data.get("clause_type", ""),
                    "reference_text": data.get("reference_text", ""),
                    "confidence": data.get("confidence", 0.0),
                }
            )
        return results

    def get_documents(self) -> list[str]:
        """Return all document names in the graph."""
        return list(self.graph.nodes())

    def get_document_count(self) -> int:
        return self.graph.number_of_nodes()

    def get_citation_count(self) -> int:
        return self.graph.number_of_edges()

    # -- Serialization -----------------------------------------------------

    def to_json(self) -> str:
        """Serialize the entire graph to a JSON string."""
        data = nx.node_link_data(self.graph, edges="links")
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "CitationGraph":
        """Deserialize a graph from a JSON string."""
        cg = cls()
        data = json.loads(json_str)
        # Handle both "links" (networkx <3.6 default) and "edges" (future default) keys
        if "edges" in data and "links" not in data:
            data["links"] = data.pop("edges")
        cg.graph = nx.node_link_graph(data, edges="links", directed=True)
        return cg

    def to_dict(self) -> dict:
        """Return a dict representation suitable for API responses."""
        return {
            "documents": list(self.graph.nodes()),
            "citations": self.get_all_citations(),
            "document_count": self.get_document_count(),
            "citation_count": self.get_citation_count(),
        }
