import json
import urllib.request

BASE = "http://127.0.0.1:10086/command"


def call(action, args=None, session="aisys"):
    body = json.dumps({"action": action, "args": args or {}, "session": session}).encode()
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    import sys
    print(json.dumps(call(sys.argv[1], json.load(open(sys.argv[2], encoding='utf-8')) if len(sys.argv) > 2 else None),
                     ensure_ascii=False)[:3000])
