import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
GRAPHQL_URL = "https://www.warcraftlogs.com/api/v2/client"


@dataclass
class WCLClient:
    client_id: str
    client_secret: str
    access_token: str | None = None

    def authenticate(self) -> str:
        resp = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        resp.raise_for_status()
        self.access_token = resp.json()["access_token"]
        return self.access_token

    def query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.access_token:
            self.authenticate()
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(json.dumps(payload["errors"], indent=2))
        return payload


def save_json(obj: dict[str, Any], path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def flatten_rankings(payload: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def walk(node: Any, path: str = "root"):
        if isinstance(node, dict):
            if {"name", "amount"}.issubset(node.keys()):
                rows.append(node | {"_path": path})
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    cols = [c for c in ["name", "spec", "className", "amount", "rank", "median", "_path"] if c in df.columns]
    extra = [c for c in df.columns if c not in cols]
    return df[cols + extra]


def summarize_json(path: str) -> str:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    df = flatten_rankings(payload)
    if df.empty:
        return "No ranking-like rows were detected. Inspect the raw JSON and adapt the GraphQL query."
    if "amount" in df.columns:
        df = df.sort_values("amount", ascending=False)
    return df.head(20).to_markdown(index=False)


def ask_agent(path: str, question: str) -> str:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    payload = Path(path).read_text(encoding="utf-8")
    client = OpenAI(api_key=api_key)
    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": "You analyze Warcraft Logs JSON and answer compactly with evidence from the provided data only.",
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nData:\n{payload[:180000]}",
            },
        ],
    )
    return resp.output_text


def build_example_query(zone: int, encounter: int) -> str:
    return f'''
query ExampleQuery {{
  worldData {{
    zone(id: {zone}) {{
      encounters {{
        id
        name
      }}
    }}
  }}
}}
'''.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch-rankings")
    f.add_argument("--zone", type=int, required=True)
    f.add_argument("--difficulty", type=int, required=False, default=4)
    f.add_argument("--encounter", type=int, required=True)
    f.add_argument("--metric", type=str, default="dps")
    f.add_argument("--out", type=str, required=True)
    f.add_argument("--query-file", type=str, default=None)

    s = sub.add_parser("summarize")
    s.add_argument("--input", type=str, required=True)

    a = sub.add_parser("ask")
    a.add_argument("--input", type=str, required=True)
    a.add_argument("--question", type=str, required=True)

    e = sub.add_parser("example-query")
    e.add_argument("--zone", type=int, required=True)
    e.add_argument("--encounter", type=int, required=True)

    args = parser.parse_args()

    if args.cmd == "example-query":
        print(build_example_query(args.zone, args.encounter))
        return

    if args.cmd == "summarize":
        print(summarize_json(args.input))
        return

    if args.cmd == "ask":
        print(ask_agent(args.input, args.question))
        return

    client_id = os.getenv("WCL_CLIENT_ID")
    client_secret = os.getenv("WCL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("WCL_CLIENT_ID and WCL_CLIENT_SECRET must be set.")

    client = WCLClient(client_id, client_secret)

    if args.query_file:
        query = Path(args.query_file).read_text(encoding="utf-8")
    else:
        query = build_example_query(args.zone, args.encounter)

    payload = client.query(query)
    save_json(payload, args.out)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
