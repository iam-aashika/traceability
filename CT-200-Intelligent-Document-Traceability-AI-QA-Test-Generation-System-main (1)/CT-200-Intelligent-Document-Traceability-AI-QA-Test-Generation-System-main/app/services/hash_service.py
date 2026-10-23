import hashlib
from pathlib import Path
from typing import Union, Optional
from app.utils.normalization import canonical_content_for_hash, slugify, normalize_text

class HashService:
    @staticmethod
    def calculate_file_hash(content: Union[bytes, str, Path]) -> str:
        """Calculate SHA-256 hash of a file or byte content."""
        hasher = hashlib.sha256()
        if isinstance(content, (str, Path)) and Path(content).is_file():
            with open(content, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
        elif isinstance(content, bytes):
            hasher.update(content)
        elif isinstance(content, str):
            hasher.update(content.encode("utf-8"))
        else:
            raise ValueError("Unsupported content type for file hashing")
        return hasher.hexdigest()

    @staticmethod
    def calculate_content_hash(heading: str, body_text: str) -> str:
        """
        Calculate deterministic SHA-256 hash of canonical heading + body_text.
        Used for staleness detection and version comparison.
        """
        canonical = canonical_content_for_hash(heading, body_text)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_logical_node_id(section_number: Optional[str], heading: str, parent_logical_id: Optional[str] = None) -> str:
        """
        Generate a stable logical node ID across document versions.
        Incorporates section number and slugified heading to ensure:
        1. Duplicate headings (e.g. 4.2 Error Codes vs 7.1 Error Codes) have distinct IDs.
        2. Unchanged sections maintain the exact same logical ID across v1 and v2.
        """
        clean_heading = normalize_text(heading)
        slug = slugify(clean_heading)
        
        if section_number:
            clean_num = section_number.strip().replace(".", "_")
            return f"sec_{clean_num}_{slug}"
        elif parent_logical_id:
            return f"{parent_logical_id}_{slug}"
        else:
            return f"sec_{slug}"

    @staticmethod
    def generate_versioned_node_id(version_id: str, logical_node_id: str) -> str:
        """Generate a version-specific unique primary key for a SectionNode."""
        return f"{version_id}_{logical_node_id}"
