import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location('wb', 'scripts/wb.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
code = open(sys.argv[1], encoding='utf-8').read()
print(json.dumps(m.call('evaluate', {'code': code}), ensure_ascii=False)[:3000])
