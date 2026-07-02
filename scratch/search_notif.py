from pathlib import Path
import os

backend_path = Path(__file__).resolve().parent.parent / "app"
search_term = "notification"

matches = []
for root, dirs, files in os.walk(backend_path):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    if search_term in content.lower():
                        matches.append(filepath)
            except Exception as e:
                pass

print(f"Found {len(matches)} files matching '{search_term}':")
for m in matches[:20]:
    print(m)
