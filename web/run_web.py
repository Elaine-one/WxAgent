import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="WeChat-Claude Web Management Panel")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    args = parser.parse_args()

    print(f"Starting WeChat-Claude Management Panel...")
    print(f"URL: http://{args.host}:{args.port}")

    uvicorn.run(
        "web.api.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
