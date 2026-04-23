import csv
import re
import unicodedata

def normalize_for_match(text: str) -> str:
    """Strip diacritics and punctuation, lowercase."""
    # Remove diacritics via NFD decomposition
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    # Remove punctuation and extra spaces, lowercase
    text = re.sub(r'[^\w\s]', '', text).lower().strip()
    return text

flag_codes = {}

with open('logs/isolist.csv', 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)  # Skip header

    for row in reader:
        if len(row) < 4:
            continue

        name = row[0].strip()
        alpha2 = row[1].strip().lower()
        alpha3 = row[2].strip().lower()
        numeric = row[3].strip()

        if not alpha2:
            continue

        # Add alpha-2
        flag_codes[alpha2] = alpha2

        # Add alpha-3
        if alpha3:
            flag_codes[alpha3] = alpha2

        # Add numeric (0-pad to 3 digits)
        if numeric:
            padded = numeric.zfill(3)
            flag_codes[padded] = alpha2

        # Add English short name (normalized)
        if name:
            normalized_name = normalize_for_match(name)
            flag_codes[normalized_name] = alpha2

# Output as Python dict for pasting into templates.py
print("FLAG_CODES = {")
for key in sorted(flag_codes.keys()):
    print(f'    "{key}": "{flag_codes[key]}",')
print("}")
