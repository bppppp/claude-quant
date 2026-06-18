import sys
guide = open(sys.argv[1]).read()
with open(sys.argv[2], 'w', encoding='utf-8') as f:
    f.write(guide)
print('OK')
