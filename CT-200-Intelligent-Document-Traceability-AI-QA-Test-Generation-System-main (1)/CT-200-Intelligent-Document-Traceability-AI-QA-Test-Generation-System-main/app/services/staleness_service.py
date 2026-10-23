import re
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session
from app.models.version import DocumentVersion
from app.models.section import SectionNode
from app.services.diff_service import DiffService
from app.schemas.generation import NodeStalenessDetail, TestTraceabilityResponse, TestCase

class StalenessService:
    @staticmethod
    def evaluate_node_staleness(
        db: Session,
        document_id: str,
        original_version_id: str,
        node_id: str,
        logical_node_id: str,
        original_heading: str,
        original_text: str,
        original_hash: str
    ) -> NodeStalenessDetail:
        """
        Evaluate staleness of a single requirement node against the latest document version.
        Performs:
        1. Exact SHA-256 hash check
        2. Numerical threshold comparison (pressure, timing, percentages, cycles)
        3. Error code comparison (E1-E9)
        4. Negation and safety constraint change detection
        5. Conservative REVIEW_REQUIRED classification for wording shifts
        """
        # Fetch latest version for document
        latest_version = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )

        original_version = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.id == original_version_id)
            .first()
        )
        orig_label = original_version.version_label if original_version else original_version_id

        if not latest_version or latest_version.id == original_version_id:
            # Pinned to latest version
            return NodeStalenessDetail(
                node_id=node_id,
                logical_node_id=logical_node_id,
                heading=original_heading,
                original_version=orig_label,
                original_hash=original_hash,
                current_version=orig_label,
                current_hash=original_hash,
                staleness_status="CURRENT",
                change_category="NONE",
                reason="Requirement corresponds to the latest document revision.",
                human_review_recommendation="No action needed. Generated test cases reflect current specification.",
                diff_text=None
            )

        # Look for matching node in latest version
        latest_node = (
            db.query(SectionNode)
            .filter(
                SectionNode.version_id == latest_version.id,
                SectionNode.logical_node_id == logical_node_id
            )
            .first()
        )

        if not latest_node:
            return NodeStalenessDetail(
                node_id=node_id,
                logical_node_id=logical_node_id,
                heading=original_heading,
                original_version=orig_label,
                original_hash=original_hash,
                current_version=latest_version.version_label,
                current_hash=None,
                staleness_status="SOURCE_REMOVED",
                change_category="DELETED",
                reason=f"Section was removed or structurally re-architected in latest version {latest_version.version_label}.",
                human_review_recommendation="Deprecate or re-map associated test cases to alternative requirements.",
                diff_text=None
            )

        # Content hash check
        if original_hash == latest_node.content_hash:
            return NodeStalenessDetail(
                node_id=node_id,
                logical_node_id=logical_node_id,
                heading=original_heading,
                original_version=orig_label,
                original_hash=original_hash,
                current_version=latest_version.version_label,
                current_hash=latest_node.content_hash,
                staleness_status="CURRENT",
                change_category="NONE",
                reason="SHA-256 content hash is identical in latest version.",
                human_review_recommendation="No action needed. Section requirement is unchanged.",
                diff_text=None
            )

        # Content changed: Perform forensic impact analysis
        diff = DiffService.generate_diff(
            original_text,
            latest_node.body_text,
            old_label=orig_label,
            new_label=latest_version.version_label
        )
        diff_text = diff["diff_text"]

        # 1. Numerical & Unit Value Check
        num_pattern = r"\b(\d+(?:\.\d+)?)\s*(mmHg|bpm|cm|seconds?|minutes?|%|cycles?|V|AA)?\b"
        old_nums = set(re.findall(num_pattern, original_text, re.IGNORECASE))
        new_nums = set(re.findall(num_pattern, latest_node.body_text, re.IGNORECASE))
        
        diff_nums_removed = old_nums - new_nums
        diff_nums_added = new_nums - old_nums

        if diff_nums_removed or diff_nums_added:
            return NodeStalenessDetail(
                node_id=node_id,
                logical_node_id=logical_node_id,
                heading=original_heading,
                original_version=orig_label,
                original_hash=original_hash,
                current_version=latest_version.version_label,
                current_hash=latest_node.content_hash,
                staleness_status="STALE",
                change_category="NUMERICAL_THRESHOLD",
                reason=f"Numerical limits or timing changed: former {list(diff_nums_removed)} replaced by {list(diff_nums_added)}.",
                human_review_recommendation="High-priority manual test case update required. Numerical tolerances, steps, or timeouts altered.",
                diff_text=diff_text
            )

        # 2. Error Code Definitions Check
        code_pattern = r"\b(E[1-9])\b"
        old_codes = set(re.findall(code_pattern, original_text))
        new_codes = set(re.findall(code_pattern, latest_node.body_text))
        if old_codes != new_codes:
            return NodeStalenessDetail(
                node_id=node_id,
                logical_node_id=logical_node_id,
                heading=original_heading,
                original_version=orig_label,
                original_hash=original_hash,
                current_version=latest_version.version_label,
                current_hash=latest_node.content_hash,
                staleness_status="STALE",
                change_category="ERROR_CODE",
                reason=f"Error code coverage changed from {sorted(list(old_codes))} to {sorted(list(new_codes))}.",
                human_review_recommendation="Update QA test scenarios to verify revised error code handling.",
                diff_text=diff_text
            )

        # 3. Negations & Safety Constraints Check
        neg_pattern = r"\b(not|never|cannot|prohibited|mandatory|contraindicated|shall|must|abort|halt|emergency)\b"
        old_negs = set(re.findall(neg_pattern, original_text, re.IGNORECASE))
        new_negs = set(re.findall(neg_pattern, latest_node.body_text, re.IGNORECASE))
        if old_negs != new_negs:
            return NodeStalenessDetail(
                node_id=node_id,
                logical_node_id=logical_node_id,
                heading=original_heading,
                original_version=orig_label,
                original_hash=original_hash,
                current_version=latest_version.version_label,
                current_hash=latest_node.content_hash,
                staleness_status="STALE",
                change_category="SAFETY_BEHAVIOR",
                reason="Safety conditions, negations, or mandatory constraints were modified.",
                human_review_recommendation="Perform regulatory safety review; update test verification steps.",
                diff_text=diff_text
            )

        # 4. Text modified without numerical or condition change
        return NodeStalenessDetail(
            node_id=node_id,
            logical_node_id=logical_node_id,
            heading=original_heading,
            original_version=orig_label,
            original_hash=original_hash,
            current_version=latest_version.version_label,
            current_hash=latest_node.content_hash,
            staleness_status="REVIEW_REQUIRED",
            change_category="TEXT_MODIFIED",
            reason="Wording modified without direct numerical or safety constraint alteration.",
            human_review_recommendation="Manual QA inspection recommended to confirm semantic equivalence.",
            diff_text=diff_text
        )

    @staticmethod
    def evaluate_generation_traceability(
        db: Session,
        generation_data: Dict[str, Any]
    ) -> TestTraceabilityResponse:
        """
        Evaluate retrieval-time staleness across all source nodes of a generation.
        """
        doc_id = generation_data["document_id"]
        orig_ver_id = generation_data["version_id"]
        orig_ver_label = generation_data.get("version_label", "v1.0")
        snapshots = generation_data.get("source_snapshots", {})

        # Find latest version
        latest_ver = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_id)
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )
        latest_ver_label = latest_ver.version_label if latest_ver else orig_ver_label

        node_details: List[NodeStalenessDetail] = []
        statuses = set()

        for nid in generation_data.get("source_node_ids", []):
            snap = snapshots.get(nid, {})
            detail = StalenessService.evaluate_node_staleness(
                db=db,
                document_id=doc_id,
                original_version_id=orig_ver_id,
                node_id=nid,
                logical_node_id=snap.get("logical_node_id", nid),
                original_heading=snap.get("heading", ""),
                original_text=snap.get("body_text", ""),
                original_hash=snap.get("content_hash", "")
            )
            node_details.append(detail)
            statuses.add(detail.staleness_status)

        # Aggregate overall status
        if "STALE" in statuses:
            overall = "STALE"
            summary = "One or more underlying requirements have changed critical thresholds or safety behaviors."
            recommendation = "Do not execute these test cases against the latest device revision until updated."
        elif "SOURCE_REMOVED" in statuses:
            overall = "SOURCE_REMOVED"
            summary = "One or more source requirement sections were removed in the latest document revision."
            recommendation = "Re-evaluate test coverage; retire or re-assign orphan test cases."
        elif "REVIEW_REQUIRED" in statuses:
            overall = "REVIEW_REQUIRED"
            summary = "Textual wording changes detected without confirmed safety-critical parameter alteration."
            recommendation = "Conduct human QA peer review to ensure verification steps remain accurate."
        else:
            overall = "CURRENT"
            summary = "All underlying source requirements are completely identical in the latest version."
            recommendation = "Test cases are fully valid for current release verification."

        test_cases = [TestCase.model_validate(tc) for tc in generation_data.get("test_cases", [])]

        return TestTraceabilityResponse(
            generation_id=generation_data["generation_id"],
            selection_id=generation_data["selection_id"],
            selection_name=generation_data.get("selection_name", ""),
            document_id=doc_id,
            original_version=orig_ver_label,
            latest_document_version=latest_ver_label,
            overall_staleness_status=overall,
            has_stale_requirements=overall != "CURRENT",
            summary_reason=summary,
            human_review_recommendation=recommendation,
            node_staleness_details=node_details,
            test_cases=test_cases,
            source_snapshot=snapshots
        )
