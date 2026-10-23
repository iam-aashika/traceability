import json
import logging
from typing import List, Dict, Optional, Tuple
from app.models.section import SectionNode
from app.services.pdf_extractor import RawSectionItem
from app.services.hash_service import HashService
from app.utils.normalization import normalize_text

logger = logging.getLogger(__name__)

class HierarchyBuilder:
    @staticmethod
    def build_hierarchy(
        document_id: str,
        version_id: str,
        raw_sections: List[RawSectionItem]
    ) -> List[SectionNode]:
        """
        Reconstruct a hierarchical document tree from sequential raw section items.
        
        Handles:
        - Duplicate headings with different section numbers or parents
        - Out-of-order section numbering (e.g. 3.4 appearing before 3.3)
        - Skipped hierarchy levels (e.g. 2.1.1.1 under 2.1)
        - Cross-page continuations and table embedding
        - Deterministic logical node ID generation
        - SHA-256 content hashing for staleness detection
        """
        nodes: List[SectionNode] = []
        # Stack entries: (section_number, level, node)
        stack: List[Tuple[Optional[str], int, SectionNode]] = []

        for index, item in enumerate(raw_sections):
            warnings = list(item.warnings)
            
            # Determine parent via prefix matching and stack unwinding
            parent_node: Optional[SectionNode] = None
            
            if item.level == 1:
                # Root level section - unwinds entire stack
                stack.clear()
            else:
                # Find appropriate parent in the stack
                # 1. First try prefix match if section_number has dot notation
                matched_in_stack = False
                if item.section_number and "." in item.section_number:
                    parts = item.section_number.split(".")
                    # Direct expected parent prefix: e.g. "3" for "3.2" or "2.1" for "2.1.1.1"
                    for depth in range(len(parts) - 1, 0, -1):
                        prefix = ".".join(parts[:depth])
                        for s_num, s_lvl, s_node in reversed(stack):
                            if s_num == prefix:
                                parent_node = s_node
                                matched_in_stack = True
                                break
                        if matched_in_stack:
                            break
                            
                # 2. If no prefix match, unwind stack until we find a node with level < item.level
                if not matched_in_stack:
                    while stack and stack[-1][1] >= item.level:
                        stack.pop()
                    if stack:
                        parent_node = stack[-1][2]

                # Check if hierarchy level was skipped
                if parent_node:
                    if item.level > parent_node.level + 1:
                        warnings.append(
                            f"Hierarchy level skipped: Section {item.section_number or item.heading} "
                            f"(level {item.level}) parented under {parent_node.section_number or parent_node.heading} "
                            f"(level {parent_node.level})."
                        )
                else:
                    warnings.append(
                        f"No parent found for subsection {item.section_number or item.heading} "
                        f"(level {item.level}). Promoted to root."
                    )

            # Generate stable logical node ID
            parent_logical_id = parent_node.logical_node_id if parent_node else None
            logical_id = HashService.generate_logical_node_id(
                section_number=item.section_number,
                heading=item.heading,
                parent_logical_id=parent_logical_id
            )

            # Version-specific unique primary key
            node_id = HashService.generate_versioned_node_id(version_id, logical_id)

            # Build hierarchical path
            if parent_node:
                path = f"{parent_node.path}/{item.section_number or logical_id}"
            else:
                path = f"/{item.section_number or logical_id}"

            # Calculate deterministic SHA-256 content hash
            content_hash = HashService.calculate_content_hash(
                heading=item.heading,
                body_text=item.body_text
            )

            full_text = f"{item.heading}\n\n{item.body_text}".strip()

            table_json = json.dumps(item.table_data) if item.table_data else None

            node = SectionNode(
                id=node_id,
                logical_node_id=logical_id,
                document_id=document_id,
                version_id=version_id,
                section_number=item.section_number,
                heading=item.heading,
                level=item.level,
                parent_id=parent_node.id if parent_node else None,
                order_index=index,
                path=path,
                body_text=item.body_text,
                full_text=full_text,
                content_hash=content_hash,
                page_start=item.page_start,
                page_end=item.page_end,
                has_table=item.has_table,
                table_data=table_json,
                extraction_confidence=item.confidence,
                extraction_warnings=json.dumps(warnings)
            )

            nodes.append(node)
            
            # Maintain stack: push current node onto stack
            stack.append((item.section_number, item.level, node))

        return nodes
