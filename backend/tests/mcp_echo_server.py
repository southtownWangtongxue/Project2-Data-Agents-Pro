"""最小 stdio MCP 测试服务器：initialize / tools/list / tools/call(echo)"""
import json
import sys


def resp(req_id, result):
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method", "")
        req_id = msg.get("id")
        if method == "initialize":
            print(resp(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-test", "version": "0.1"},
            }), flush=True)
        elif method == "tools/list":
            print(resp(req_id, {"tools": [{
                "name": "echo",
                "description": "原样返回输入文本，用于测试",
                "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            }]}), flush=True)
        elif method == "tools/call":
            args = msg.get("params", {}).get("arguments", {})
            print(resp(req_id, {
                "content": [{"type": "text", "text": f"echo: {args.get('text', '')}"}],
                "isError": False,
            }), flush=True)
        elif req_id is not None:
            print(resp(req_id, {}), flush=True)


if __name__ == "__main__":
    main()
