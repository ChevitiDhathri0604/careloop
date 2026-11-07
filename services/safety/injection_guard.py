"""
CareLoop Prompt-Injection Guard
Inspects all untrusted free-text inputs (e.g., patient SMS replies, patient portal notes)
for prompt injection, instruction smuggling, jailbreaks, and data-exfiltration payloads.
Blocks execution and logs the security threat to the immutable audit trail.
"""

import re
from typing import Dict, Any, Tuple

# Suspicious instruction patterns
INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"(?i)system\s+prompt\s+override",
    r"(?i)you\s+are\s+now\s+(in\s+)?(developer\s+mode|dan|unrestricted)",
    r"(?i)(forward|send|email|post)\s+.*?(records|phi|patient\s+data|secrets?).*?\s+to\s+",
    r"(?i)https?://[^\s]+(exfil|evil|collect|attacker)",
    r"(?i)print\s+(the\s+)?(system\s+prompt|token|bearer|keys?)",
    r"(?i)drop\s+table",
    r"(?i)bypass\s+(safety|guardrails?|filter)",
    r"(?i)<script[\s>]",
    r"(?i)!\[.*?\]\(https?://.*?/.*?\)"  # Markdown image exfiltration
]

class PromptInjectionGuard:
    def __init__(self):
        self.compiled_patterns = [re.compile(p) for p in INJECTION_PATTERNS]
        self.blocked_attempts_count = 0

    def inspect_text(self, text: str, source_identifier: str = "patient_sms") -> Tuple[bool, str, Dict[str, Any]]:
        """
        Scans free text for injection attempts.
        Returns: (is_safe: bool, reason: str, metadata: dict)
        """
        if not text or not isinstance(text, str):
            return True, "Empty text", {}

        for pattern in self.compiled_patterns:
            match = pattern.search(text)
            if match:
                self.blocked_attempts_count += 1
                matched_snippet = match.group(0)
                reason = f"Prompt-injection attack detected: matched pattern '{matched_snippet}'"
                
                # Import ledger to log security event
                from services.control_plane.ledger import action_ledger
                action_ledger.record_audit(
                    actor="injection-guard",
                    action_type="SECURITY_PROMPT_INJECTION_BLOCKED",
                    details={
                        "source": source_identifier,
                        "matchedPattern": pattern.pattern,
                        "flaggedSnippet": matched_snippet,
                        "status": "BLOCKED"
                    }
                )

                return False, reason, {
                    "matchedPattern": pattern.pattern,
                    "flaggedSnippet": matched_snippet,
                    "severity": "CRITICAL"
                }

        return True, "Clean text", {"status": "PASSED"}

injection_guard = PromptInjectionGuard()
