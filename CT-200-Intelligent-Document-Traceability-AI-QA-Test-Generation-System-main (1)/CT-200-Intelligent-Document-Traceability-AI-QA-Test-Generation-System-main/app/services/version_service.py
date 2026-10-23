import difflib
import logging
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.version import DocumentVersion
from app.models.section import SectionNode
from app.services.diff_service import DiffService
from app.utils.normalization import normalize_text, slugify

logger = logging.getLogger(__name__)

class VersionMatchResult:
    def __init__(
        self,
        status: str,  # UNCHANGED, MODIFIED, ADDED, REMOVED, MOVED, REVIEW_REQUIRED
        old_node: Optional[SectionNode] = None,
        new_node: Optional[SectionNode] = None,
        confidence: float = 1.0,
        reason: str = "",
        diff_summary: Optional[Dict[str, Any]] = None
    ):
        self.status = status
        self.old_node = old_node
        self.new_node = new_node
        self.confidence = confidence
        self.reason = reason
        self.diff_summary = diff_summary

class VersionService:
    @staticmethod
    def match_nodes(
        old_nodes: List[SectionNode],
        new_nodes: List[SectionNode]
    ) -> List[VersionMatchResult]:
        """
        Compare sections between two document versions using a multi-stage matching strategy:
        Stage 1: Primary match on stable logical_node_id.
        Stage 2: Fallback match on normalized hierarchical path.
        Stage 3: Fuzzy heading match within parent context.
        Stage 4: Content similarity fallback.
        """
        results: List[VersionMatchResult] = []
        new_nodes_by_logical_id = {n.logical_node_id: n for n in new_nodes}
        matched_new_ids = set()

        for old in old_nodes:
            new_node = new_nodes_by_logical_id.get(old.logical_node_id)
            match_confidence = 1.0
            match_reason = ""

            # Fallback 1: Path match if logical_node_id didn't match directly
            if not new_node:
                for cand in new_nodes:
                    if cand.id not in matched_new_ids and cand.path == old.path:
                        new_node = cand
                        match_confidence = 0.90
                        match_reason = "Matched by identical hierarchical path"
                        break

            # Fallback 2: Heading similarity within same parent level
            if not new_node:
                old_slug = slugify(old.heading)
                best_ratio = 0.0
                best_cand = None
                for cand in new_nodes:
                    if cand.id not in matched_new_ids and cand.level == old.level:
                        ratio = difflib.SequenceMatcher(None, old_slug, slugify(cand.heading)).ratio()
                        if ratio > best_ratio and ratio >= 0.85:
                            best_ratio = ratio
                            best_cand = cand
                if best_cand:
                    new_node = best_cand
                    match_confidence = round(best_ratio, 2)
                    match_reason = f"Fuzzy heading match ({best_ratio:.2f}) at level {old.level}"

            # Fallback 3: Content similarity fallback (detecting renumbered sections)
            if not new_node and len(old.body_text) > 50:
                best_ratio = 0.0
                best_cand = None
                for cand in new_nodes:
                    if cand.id not in matched_new_ids:
                        ratio = difflib.SequenceMatcher(None, old.body_text, cand.body_text).ratio()
                        if ratio > best_ratio and ratio >= 0.80:
                            best_ratio = ratio
                            best_cand = cand
                if best_cand:
                    new_node = best_cand
                    match_confidence = round(best_ratio, 2)
                    match_reason = f"High body text similarity ({best_ratio:.2f}) suggesting renumbering"

            if not new_node:
                # Node removed in newer version
                results.append(VersionMatchResult(
                    status="REMOVED",
                    old_node=old,
                    new_node=None,
                    confidence=1.0,
                    reason=f"Section {old.section_number or ''} '{old.heading}' does not exist in target version."
                ))
                continue

            matched_new_ids.add(new_node.id)

            # Determine change status
            if old.content_hash == new_node.content_hash:
                if old.path == new_node.path:
                    status = "UNCHANGED"
                    reason = "Content and structural position are identical."
                    diff = None
                else:
                    status = "MOVED"
                    reason = f"Content is identical but section moved from '{old.path}' to '{new_node.path}'."
                    diff = None
            else:
                # Content changed
                status = "MODIFIED"
                diff = DiffService.generate_diff(
                    old.body_text,
                    new_node.body_text,
                    old_label=f"v{old.version_id}",
                    new_label=f"v{new_node.version_id}"
                )
                reason = f"Content changed: {len(diff['added_lines'])} line(s) added, {len(diff['removed_lines'])} line(s) removed."
                if match_confidence < 0.85:
                    status = "REVIEW_REQUIRED"
                    reason += " [Uncertain match confidence requires human verification]"

            results.append(VersionMatchResult(
                status=status,
                old_node=old,
                new_node=new_node,
                confidence=match_confidence,
                reason=match_reason or reason,
                diff_summary=diff
            ))

        # Check for newly ADDED sections
        for new in new_nodes:
            if new.id not in matched_new_ids:
                results.append(VersionMatchResult(
                    status="ADDED",
                    old_node=None,
                    new_node=new,
                    confidence=1.0,
                    reason=f"New section {new.section_number or ''} '{new.heading}' introduced in this version."
                ))

        return results

    @staticmethod
    def compare_node_across_versions(
        db: Session,
        node_id: str
    ) -> Dict[str, Any]:
        """
        Given a specific node_id, determine its change status compared to the latest version.
        """
        target_node = db.query(SectionNode).filter(SectionNode.id == node_id).first()
        if not target_node:
            raise ValueError(f"Section node {node_id} not found.")

        # Find all versions for this document
        versions = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == target_node.document_id)
            .order_by(DocumentVersion.version_number.desc())
            .all()
        )
        if not versions:
            return {
                "node_id": node_id,
                "logical_node_id": target_node.logical_node_id,
                "document_id": target_node.document_id,
                "version_id": target_node.version_id,
                "status": "UNCHANGED",
                "has_changed": False,
                "details": "Only one version exists.",
                "diff_summary": None
            }

        latest_version = versions[0]
        current_version_node = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.id == target_node.version_id)
            .first()
        )

        # If already on latest version, compare against previous version if available
        if target_node.version_id == latest_version.id:
            if len(versions) > 1:
                prev_version = versions[1]
                prev_node = (
                    db.query(SectionNode)
                    .filter(
                        SectionNode.version_id == prev_version.id,
                        SectionNode.logical_node_id == target_node.logical_node_id
                    )
                    .first()
                )
                if not prev_node:
                    return {
                        "node_id": node_id,
                        "logical_node_id": target_node.logical_node_id,
                        "document_id": target_node.document_id,
                        "version_id": target_node.version_id,
                        "status": "ADDED",
                        "has_changed": True,
                        "details": f"Section was newly added in {latest_version.version_label}.",
                        "diff_summary": None
                    }
                has_changed = prev_node.content_hash != target_node.content_hash
                status = "MODIFIED" if has_changed else "UNCHANGED"
                diff = None
                if has_changed:
                    diff = DiffService.generate_diff(
                        prev_node.body_text,
                        target_node.body_text,
                        old_label=prev_version.version_label,
                        new_label=latest_version.version_label
                    )
                return {
                    "node_id": node_id,
                    "logical_node_id": target_node.logical_node_id,
                    "document_id": target_node.document_id,
                    "version_id": target_node.version_id,
                    "status": status,
                    "has_changed": has_changed,
                    "details": f"Compared with previous version {prev_version.version_label}.",
                    "diff_summary": {
                        "old_version": prev_version.version_label,
                        "current_version": latest_version.version_label,
                        "old_hash": prev_node.content_hash,
                        "current_hash": target_node.content_hash,
                        "diff_text": diff["diff_text"] if diff else "",
                        "added_lines": diff["added_lines"] if diff else [],
                        "removed_lines": diff["removed_lines"] if diff else []
                    } if diff else None
                }
            else:
                return {
                    "node_id": node_id,
                    "logical_node_id": target_node.logical_node_id,
                    "document_id": target_node.document_id,
                    "version_id": target_node.version_id,
                    "status": "UNCHANGED",
                    "has_changed": False,
                    "details": "Single version document. No previous revisions exist.",
                    "diff_summary": None
                }

        # Target node belongs to older version; compare against latest version
        latest_node = (
            db.query(SectionNode)
            .filter(
                SectionNode.version_id == latest_version.id,
                SectionNode.logical_node_id == target_node.logical_node_id
            )
            .first()
        )

        if not latest_node:
            return {
                "node_id": node_id,
                "logical_node_id": target_node.logical_node_id,
                "document_id": target_node.document_id,
                "version_id": target_node.version_id,
                "status": "REMOVED",
                "has_changed": True,
                "details": f"Section was removed or significantly restructured in latest version {latest_version.version_label}.",
                "diff_summary": None
            }

        has_changed = target_node.content_hash != latest_node.content_hash
        status = "MODIFIED" if has_changed else "UNCHANGED"
        diff = None
        if has_changed:
            diff = DiffService.generate_diff(
                target_node.body_text,
                latest_node.body_text,
                old_label=current_version_node.version_label if current_version_node else target_node.version_id,
                new_label=latest_version.version_label
            )

        return {
            "node_id": node_id,
            "logical_node_id": target_node.logical_node_id,
            "document_id": target_node.document_id,
            "version_id": target_node.version_id,
            "status": status,
            "has_changed": has_changed,
            "details": f"Compared with latest version {latest_version.version_label}.",
            "diff_summary": {
                "old_version": current_version_node.version_label if current_version_node else target_node.version_id,
                "current_version": latest_version.version_label,
                "old_hash": target_node.content_hash,
                "current_hash": latest_node.content_hash,
                "diff_text": diff["diff_text"] if diff else "",
                "added_lines": diff["added_lines"] if diff else [],
                "removed_lines": diff["removed_lines"] if diff else []
            } if diff else None
        }
