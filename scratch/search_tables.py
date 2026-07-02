from pathlib import Path
import os

models_path = Path(__file__).resolve().parent.parent / "app" / "models"
files = os.listdir(models_path)
print("Available model files:")
print(files)

# search for content
for file in files:
    if file.endswith(".py"):
        try:
            with open(os.path.join(models_path, file), "r") as f:
                content = f.read()
                for keyword in ["checklist", "document", "revision"]:
                    if keyword in content.lower():
                        print(f"Keyword '{keyword}' found in: {file}")
        except Exception:
            pass
