import os
import glob

migrations_dir = r"c:\Users\91891\OneDrive\Desktop\cognitive\cognitive-backend\migrations\versions"
files = glob.glob(os.path.join(migrations_dir, "*.py"))

down_revisions = set()
revisions = {}

for f in files:
    with open(f, "r", encoding="utf-8") as file:
        content = file.read()
        rev = None
        down_rev = None
        for line in content.split("\n"):
            if line.startswith("revision ="):
                rev = line.split("=")[1].strip().strip("'\"")
            elif line.startswith("down_revision ="):
                val = line.split("=")[1].strip().strip("'\"")
                if val != 'None':
                    down_revisions.add(val)
        if rev:
            revisions[rev] = f

head = [r for r in revisions.keys() if r not in down_revisions]
print(head)
