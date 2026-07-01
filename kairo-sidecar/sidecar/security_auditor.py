import re


class SecurityAuditor:
    def __init__(self, strict: bool = False):
        self.strict = strict
        self.keywords = ["confidential", "trade secret", "internal use only", "proprietary"]

    def audit(self, text: str) -> str:
        """
        Audit the input text for confidential keywords.
        If strict is True, raises ValueError on match.
        Otherwise, redacts the matched terms and returns the redacted text.
        """
        result_text = text
        for keyword in self.keywords:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            if pattern.search(result_text):
                if self.strict:
                    raise ValueError(f"Confidential data detected: {keyword}")
                else:
                    result_text = pattern.sub("[REDACTED]", result_text)
        return result_text
