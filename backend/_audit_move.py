"""一次性審計腳本（用完即刪）：盤點 database.py 中 Epic 1 區塊的邊界與對外依賴。"""
import ast
import builtins

PATH = "database.py"
src = open(PATH, encoding="utf-8").read()
lines = src.splitlines(keepends=True)
tree = ast.parse(src)

start0 = None
for i, ln in enumerate(lines):
    if "【Epic 1 新增】四類模板" in ln:
        start0 = i
        break
print("banner 0-based line =", start0, "| 1-based =", start0 + 1)
for j in range(max(0, start0 - 3), start0 + 3):
    print("  %5d | %s" % (j + 1, lines[j].rstrip()))
block_start = start0 - 1          # 含上一行的 ==== 分隔線
print("block_start(1-based) =", block_start + 1, "| total lines =", len(lines))

pre_defs, local_defs, used = set(), set(), set()
for node in tree.body:
    bucket_defs = pre_defs if node.lineno < block_start + 1 else local_defs
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bucket_defs.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bucket_defs.add(n.id)

for node in tree.body:
    if node.lineno < block_start + 1:
        continue
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            pass

is_builtin = lambda n: hasattr(builtins, n)
print("\n[需從 database.py 取得] :", sorted(n for n in used if n not in local_defs and not is_builtin(n) and n in pre_defs))
print("\n[既非本區塊、也非前置定義] :", sorted(n for n in used if n not in local_defs and not is_builtin(n) and n not in pre_defs))
print("\n[前置定義清單中含 herbs / role 常量者] :", sorted(n for n in pre_defs if "PRESCRIPTION" in n or "HERB" in n or "ROLE" in n))
