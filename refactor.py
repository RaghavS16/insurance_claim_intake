import os

REPLACEMENTS = {
    "claim_type": "insurance_type",
    "damage_description": "event_description",
    "incident_date": "event_date",
    "claimed_amount": "estimated_claim_amount",
}

def process_file(filepath):
    if not filepath.endswith(('.py', '.tsx', '.ts', '.sql')):
        return
    if "constants.py" in filepath or "refactor.py" in filepath:
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for old, new in REPLACEMENTS.items():
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, _, files in os.walk(r"c:\Users\ragha\Desktop\insurance_claim_intake"):
    if "node_modules" in root or ".git" in root or ".next" in root or "venv" in root:
        continue
    for file in files:
        process_file(os.path.join(root, file))
