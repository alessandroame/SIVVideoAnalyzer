import os

def ensure_arrow_icons() -> tuple[str, str]:
    """Genera le icone SVG ciano su disco se non esistono e restituisce i percorsi formattati per QSS."""
    icons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons")
    os.makedirs(icons_dir, exist_ok=True)
    up_path = os.path.abspath(os.path.join(icons_dir, "arrow_up.svg")).replace("\\", "/")
    down_path = os.path.abspath(os.path.join(icons_dir, "arrow_down.svg")).replace("\\", "/")
    
    if not os.path.exists(up_path):
        with open(up_path, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"><polygon points="12,5 21,18 3,18" fill="#38bdf8"/></svg>')
            
    if not os.path.exists(down_path):
        with open(down_path, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"><polygon points="3,6 21,6 12,19" fill="#38bdf8"/></svg>')
            
    return up_path, down_path
