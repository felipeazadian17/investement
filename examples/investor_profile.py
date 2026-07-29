import argparse
import json
from dataclasses import asdict
from pathlib import Path

from investement.agents import InvestorProfileAgent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    profile = InvestorProfileAgent().create_from_file(args.profile)
    print(json.dumps(asdict(profile), indent=2, default=json_default))


def json_default(value):
    if isinstance(value, frozenset):
        return sorted(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"cannot serialize {type(value).__name__}")


if __name__ == "__main__":
    main()
