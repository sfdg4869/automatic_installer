def route_prompt(text: str, extra_vars: dict = None) -> str:
    """
    Rout the installation to the correct agent/executor based on keywords
    in the prompt text or parsed variables.
    """
    if not text:
        text = ""
        
    text_lower = text.lower()
    
    # 1. Check Extra Vars if parsed
    if extra_vars:
        keys_lower = [k.lower() for k in extra_vars.keys()]
        if any("pjs" in k or "node" in k or "js" in k for k in keys_lower):
            return "pjs"
        if any("rts" in k or "ipc" in k for k in keys_lower):
            return "daemon"

    # 2. Check Text Clues
    # PJS should take absolute precedence if explicitly mentioned in the file name or prompt
    if "pjs" in text_lower or "platform.tar" in text_lower or "platformjs" in text_lower:
        return "pjs"
        
    if "dgm" in text_lower or "dg_m" in text_lower or "master.tar" in text_lower or "dg_" in text_lower or "datagather" in text_lower:
        return "dgm"
        
    if "dgs" in text_lower or "dg_s" in text_lower or "slave.tar" in text_lower:
        return "dgs"
        
    if "rts" in text_lower or "daemon" in text_lower or "ipc_key" in text_lower or "pmon_name" in text_lower:
        return "daemon"
        
    # Default
    return "daemon"
