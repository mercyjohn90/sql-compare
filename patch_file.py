import re

with open('.jules/sentinel.md', 'r', encoding='utf-8') as f:
    content = f.read()

# I need to change the Prevention line
# from:
# **Prevention:** The app was found to be sufficiently secure against standard low-hanging vulnerabilities.
# to:
# **Prevention:** No vulnerabilities were identified in the evaluated areas before the review was halted.

content = content.replace(
    '**Prevention:** The app was found to be sufficiently secure against standard low-hanging vulnerabilities.',
    '**Prevention:** No vulnerabilities were identified in the evaluated areas before the review was halted.'
)

with open('.jules/sentinel.md', 'w', encoding='utf-8') as f:
    f.write(content)
