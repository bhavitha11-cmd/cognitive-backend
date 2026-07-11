with open("app/routers/part.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace require_permission("Projects" with require_permission("Parts"
new_content = content.replace('require_permission("Projects"', 'require_permission("Parts"')

with open("app/routers/part.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("Replacement complete inside app/routers/part.py")
