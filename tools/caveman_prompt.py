import os

def wrap_with_caveman(system_prompt: str) -> str:
    """
    Wraps the system prompt with Caveman rules to save output tokens.
    Leverages settings from the environment: CAVEMAN_MODE (lite, full, ultra).
    Defaults to 'full' mode.
    """
    mode = os.environ.get("CAVEMAN_MODE", "full").lower()
    
    if mode == "lite":
        caveman_instruction = (
            "\n\n[CONCISE RULE] Output response concisely. "
            "Avoid conversational fluff, introductory phrases, or polite greetings. "
            "Deliver direct technical answers."
        )
    elif mode == "ultra":
        caveman_instruction = (
            "\n\n[CAVEMAN RULE - ULTRA COMPRESSED] Output minimal words. "
            "Use telegraphic symbols and notes. Avoid complete sentences where simple list items fit. "
            "Output code blocks fully and intact, but compress explanation prose to the absolute minimum."
        )
    else: # full
        caveman_instruction = (
            "\n\n[CAVEMAN RULE] Use telegraphic technical style. "
            "Eliminate conversational padding, pleasantries, or verbose reasoning steps. "
            "Keep technical explanations to direct bulleted facts. Code blocks MUST remain fully complete and unmodified."
        )
        
    return system_prompt + caveman_instruction
