"""Reproducible source map for audited HEAD; never imports target code."""
import ast
import subprocess
from evaluation.common import ROOT,EVAL,write,digest,commit

def main():
    names=subprocess.check_output(['git','ls-tree','-rz','--name-only','HEAD'],cwd=ROOT).decode('utf-8').rstrip('\0').split('\0')
    rows=[];lines=['# Карта исходников и зависимостей','',f'Исходный commit: `{commit()}`. Только файлы исходного tracked дерева; binary/generated не читаются построчно.','', '## Полное значимое дерево','', '```text',*names,'```','', '## Собственные Python-модули: функции и импорты','']
    for name in names:
        p=ROOT/name
        item=dict(path=name,bytes=p.stat().st_size,sha256=digest(p.read_bytes()))
        if p.suffix=='.py':
            tree=ast.parse(p.read_text(encoding='utf-8'));functions=[];imports=[]
            for n in ast.walk(tree):
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):functions.append(dict(name=n.name,line=n.lineno,end=n.end_lineno,kind=type(n).__name__))
                elif isinstance(n,ast.Import):imports.extend(a.name for a in n.names)
                elif isinstance(n,ast.ImportFrom):imports.append('.'*n.level+(n.module or ''))
            item.update(functions=functions,imports=sorted(set(imports)))
            lines.extend([f'### {name}', '', 'Импорты: '+', '.join(item['imports']), '', '| Символ | Строка | Тип |','|---|---:|---|'])
            lines.extend(f'| {f["name"]} | [{f["line"]}](../{name}#L{f["line"]}) | {f["kind"]} |' for f in sorted(functions,key=lambda f:f['line']))
            lines.append('')
        rows.append(item)
    (EVAL/'SOURCE_MAP.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write(EVAL/'reports/source-inventory.json',dict(commit=commit(),files=rows,tracked_files=len(names)))

if __name__=='__main__':main()
