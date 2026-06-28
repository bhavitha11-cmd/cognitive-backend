import os

models_path = r"c:\Users\LLChowdary\OneDrive - Cognitive Engineering Technologies Pvt Ltd\Desktop\COGNITIVE\cognitive-backend\app\models"
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
