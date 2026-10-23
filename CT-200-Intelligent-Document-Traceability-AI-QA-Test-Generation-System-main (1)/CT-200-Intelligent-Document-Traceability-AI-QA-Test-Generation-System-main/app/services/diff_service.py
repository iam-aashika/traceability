import difflib
from typing import List, Dict, Any, Optional

class DiffService:
    @staticmethod
    def generate_diff(
        old_text: str,
        new_text: str,
        old_label: str = "v1",
        new_label: str = "v2"
    ) -> Dict[str, Any]:
        """
        Generate a lightweight unified diff and line-level changes between two text versions.
        """
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        diff_gen = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_label,
            tofile=new_label,
            lineterm=""
        )
        diff_text = "\n".join(diff_gen)

        added_lines: List[str] = []
        removed_lines: List[str] = []

        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:].strip())
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines.append(line[1:].strip())

        return {
            "diff_text": diff_text,
            "added_lines": [l for l in added_lines if l],
            "removed_lines": [l for l in removed_lines if l]
        }
