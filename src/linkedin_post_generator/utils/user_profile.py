import re
from pathlib import Path


def load_user_profile() -> dict:
    """Parse knowledge/user_preference.txt into a structured dict."""
    knowledge_path = Path(__file__).parent.parent.parent.parent / "knowledge" / "user_preference.txt"

    if not knowledge_path.exists():
        return {
            "name": "AI Professional",
            "title": "AI Engineer",
            "location": "Melbourne, Australia",
        }

    text = knowledge_path.read_text()

    name_match = re.search(r"User name is (.+?)\.", text)
    title_match = re.search(r"User is an? (.+?)\.", text)
    location_match = re.search(r"User is based in (.+?)\.", text)

    return {
        "name": name_match.group(1) if name_match else "AI Professional",
        "title": title_match.group(1) if title_match else "AI Engineer",
        "location": location_match.group(1) if location_match else "Melbourne, Australia",
    }
