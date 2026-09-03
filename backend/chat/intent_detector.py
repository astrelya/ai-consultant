import re

def detect_brainstorm_intent(message: str) -> bool:
    """
    Detects if the user message indicates an intent to brainstorm.
    Keywords: brainstorm, ideate, idea for, think through, sketch, plan.
    Does not trigger on: 'describe the architecture', 'my idea is to build X, here's the spec:'.
    """
    # Negative cases
    if "describe the architecture" in message.lower():
        return False
    if "my idea is to build" in message.lower() and "here's the spec" in message.lower():
        return False
        
    # Keywords
    keywords = [
        r'\bbrainstorm\b',
        r'\bideate\b',
        r'\bidea for\b',
        r'\bthink through\b',
        r'\bsketch\b',
        r'^plan\b',
        r'\blet me plan\b',
        r'\blet\'s plan\b'
    ]
    
    for pattern in keywords:
        if re.search(pattern, message, re.IGNORECASE):
            return True
            
    return False


def detect_spec_review_intent(message: str) -> bool:
    """
    Detects if the user message indicates an intent to review/validate a spec.
    Keywords: 'review this spec', 'analyze this spec', 'validate this spec',
              'check this spec', 'review my spec', 'analyze my spec'.
    Uses simple string matching (case-insensitive) — not an LLM call.
    Returns True if message contains a spec review intent keyword.
    Returns False otherwise.
    """
    keywords = [
        r'review (this|my|the) spec',
        r'analyze (this|my|the) spec',
        r'analyse (this|my|the) spec',
        r'validate (this|my|the) spec',
        r'check (this|my|the) spec',
        r'review this spec',
        r'analyze this spec',
    ]

    for pattern in keywords:
        if re.search(pattern, message, re.IGNORECASE):
            return True

    return False


def detect_direct_implementation_intent(message: str) -> bool:
    """
    Detects if the user message indicates an intent to directly implement a spec.
    Keywords: 'implement this spec', 'build this spec', 'use this spec and build it'.
    Uses simple string matching (case-insensitive) — not an LLM call.
    """
    keywords = [
        r'implement this spec',
        r'build this spec',
        r'use this spec and build it',
        r'implement (this|my|the) spec',
        r'build (this|my|the) spec',
        r'execute this spec',
    ]

    for pattern in keywords:
        if re.search(pattern, message, re.IGNORECASE):
            return True

    return False


def detect_generate_tickets_intent(message: str) -> bool:
    """Trigger real ticket generation from the saved spec."""
    patterns = [
        r'\bg[ée]n[ée]re[rz]?\s+(le|les|des|un|mes|nos)?\s*tickets?\b',
        r'\bcr[ée]e[rz]?\s+(le|les|des|un|mes|nos)?\s*tickets?\b',
        r'\bfai[st]?\s+(le|les|des)?\s*tickets?\b',
        r'\bgenerate\s+(the\s+)?tickets?\b',
        r'\bcreate\s+(the\s+)?tickets?\b',
        r'\bmake\s+(the\s+)?tickets?\b',
    ]
    for p in patterns:
        if re.search(p, message, re.IGNORECASE):
            return True
    return False


def detect_execute_intent(message: str) -> bool:
    """Trigger real execution of the generated tickets by the supervisor."""
    patterns = [
        r'\bimpl[ée]mente[rz]?\s+(le\s+)?projet\b',
        r'\bcommence[rz]?\s+l\'?impl[ée]mentation\b',
        r'\bfai[st]?\s+l\'?impl[ée]mentation\b',
        r'\blance[rz]?\s+(le\s+)?d[ée]veloppement\b',
        r'\bd[ée]marre[rz]?\s+l\'?impl[ée]mentation\b',
        r'\bstart\s+(the\s+)?(dev|development|implementation)\b',
        r'\bexecute\s+(the\s+)?tickets?\b',
        r'\brun\s+(the\s+)?tickets?\b',
        r'\bimplement\s+(the\s+)?project\b',
    ]
    for p in patterns:
        if re.search(p, message, re.IGNORECASE):
            return True
    return False
