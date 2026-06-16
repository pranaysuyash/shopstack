"""Aggressively fix all broken f-strings in primitives.py."""
import ast
import sys
import re

path = "shopstack/ui/components/primitives.py"
with open(path) as f:
    content = f.read()

# Strategy: replace ALL f'...' with f"..." (and handle the closing quote properly)
# Then handle the remaining issues

lines = content.split("\n")
fixed_lines = []
for line in lines:
    original = line

    # Fix 1: f"...content with " inside..." → f'...content with " inside...'
    # We need to be careful: the f-string might span multiple lines
    # For now, handle single-line cases

    # Fix 2: f'...content...' where content has ' → change to f"..."
    if "f'" in line:
        # Check if this is a broken f-string
        # Simple heuristic: count single quotes in the f-string portion
        # If > 2, it's broken
        # Find the f' and the next non-escaped '
        stripped = line.lstrip()
        if stripped.startswith("f'"):
            # Find the matching closing '
            # The f-string ends with ' (possibly followed by > or })
            # But if there are nested ', the first ' closes the f-string
            # We need to find the LAST ' before end of expression
            # Simple approach: find the last ' in the line
            rest = stripped[2:]
            # The f-string should end with ' (possibly followed by > or })
            # But if there are more than 2 ', we need to fix
            quote_count = rest.count("'")
            if quote_count > 1:
                # Find the last '
                last_quote = rest.rfind("'")
                inner = rest[:last_quote]
                after = rest[last_quote + 1:]
                indent = line[:len(line) - len(stripped)]
                line = indent + 'f"' + inner + '"' + after

    # Fix 3: f"...content with " inside..." → f'...content with " inside...'
    if 'f"' in line:
        stripped = line.lstrip()
        if stripped.startswith('f"'):
            rest = stripped[2:]
            # Check if the f-string has nested "
            # Simple heuristic: if the f-string is on a single line and has > 2 "
            if not stripped.startswith('f"""'):
                quote_count = rest.count('"')
                if quote_count > 1:
                    last_quote = rest.rfind('"')
                    inner = rest[:last_quote]
                    after = rest[last_quote + 1:]
                    # Only fix if the inner has " (nested quotes)
                    if '"' in inner:
                        indent = line[:len(line) - len(stripped)]
                        line = indent + "f'" + inner + "'" + after

    # Fix 4: f" that ends with ' (mismatched quotes)
    # Pattern: f"...content...' (should be f"...content...")
    if 'f"' in line:
        # Check if the line ends with ' (single quote) but starts with f"
        stripped = line.rstrip()
        if stripped.startswith('f"') and stripped.endswith("'"):
            # Change the ending ' to "
            line = line.rstrip() + '"'

    # Fix 5: </span>' → </span>" (missing closing quote on f-string)
    line = line.replace("</span>' +", '</span>" +')
    line = line.replace("</span>'\n", '</span>"\n')
    line = line.replace("</div>'\n", '</div>"\n')
    line = line.replace("</div>' +", '</div>" +')

    fixed_lines.append(line)

fixed = "\n".join(fixed_lines)
with open(path, "w") as f:
    f.write(fixed)

# Check syntax
try:
    ast.parse(fixed)
    print("OK - file parses")
    sys.exit(0)
except SyntaxError as e:
    print(f"Still broken at line {e.lineno}: {e.msg}")
    lines = fixed.split("\n")
    for i in range(max(0, e.lineno - 3), min(len(lines), e.lineno + 3)):
        marker = ">>>" if i + 1 == e.lineno else "   "
        print(f"{marker} {i + 1}: {lines[i]}")
    sys.exit(1)
