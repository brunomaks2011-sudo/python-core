#!/usr/bin/env python3
"""Cross-module reference check for the Luau sources.

luau-check analyses each file on its own (require() results are `any`), so a
call such as `HUD.setVisible(...)` is never checked against HUD.luau. This
script resolves every `local X = require(...)` to its source file, collects
the members that module defines, and reports any `X.member` / `X:member` use
that the module does not define.

Usage: python3 Tools/xref_check.py   (exit code 1 when problems are found)
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "Assets" / "Scripts"

# Rojo mapping (default.project.json): instance path -> folder on disk
MOUNTS = {
    "ReplicatedStorage.Shared": SCRIPTS / "Shared",
    "ServerScriptService.Server": SCRIPTS / "Server",
    "StarterPlayerScripts.Client": SCRIPTS / "Client",
    "ReplicatedFirst.Loading": SCRIPTS / "ReplicatedFirst",
}

REQ = re.compile(r"^local\s+(\w+)\s*=\s*require\(([\w.]+)\)", re.M)
ALIAS = re.compile(r"^local\s+(\w+)\s*=\s*(script(?:\.Parent)*)\s*$", re.M)
STRIP_STRINGS = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|\[(=*)\[.*?\]\1\]', re.S)
COMMENTS = re.compile(r"--\[(=*)\[.*?\]\1\]|--[^\n]*", re.S)


def module_name(path: pathlib.Path) -> str:
    n = path.name
    for suffix in (".server.luau", ".client.luau", ".luau"):
        if n.endswith(suffix):
            return n[: -len(suffix)]
    return n


def resolve(src: pathlib.Path, expr: str, aliases: dict) -> pathlib.Path | None:
    parts = expr.split(".")
    if parts[0] in aliases:
        parts = aliases[parts[0]].split(".") + parts[1:]
    if parts[0] == "script":
        # script = the module itself; .Parent walks up the folder tree
        node = src
        i = 1
        while i < len(parts) and parts[i] == "Parent":
            node = node.parent
            i += 1
        # init-less layout: script.Parent of Foo.luau is its directory
        rest = parts[i:]
        cur = node if node.is_dir() else node.parent
        for p in rest[:-1]:
            cur = cur / p
        return cur / (rest[-1] + ".luau") if rest else None
    for mount, folder in MOUNTS.items():
        mp = mount.split(".")
        if parts[: len(mp)] == mp:
            rest = parts[len(mp):]
            if not rest:
                return None
            cur = folder
            for p in rest[:-1]:
                cur = cur / p
            return cur / (rest[-1] + ".luau")
    return None


def clean(text: str) -> str:
    text = COMMENTS.sub("", text)
    return STRIP_STRINGS.sub('""', text)


def defined_members(path: pathlib.Path) -> set[str] | None:
    text = clean(path.read_text())
    m = re.search(r"^return\s+(\w+)\s*$", text, re.M)
    if not m:
        return None  # returns an expression; cannot tell
    name = m.group(1)
    members = set(re.findall(rf"^\s*function\s+{name}[.:](\w+)", text, re.M))
    members |= set(re.findall(r"^export\s+type\s+(\w+)", text, re.M))
    members |= set(re.findall(rf"^\s*{name}\.(\w+)\s*=", text, re.M))
    # fields in the table constructor: local Name = { a = ..., b = ... }
    ctor = re.search(rf"^local\s+{name}\s*(?::[^=]+)?=\s*\{{", text, re.M)
    if ctor:
        depth, i, start = 0, ctor.end() - 1, ctor.end()
        while i < len(text):
            c = text[i]
            if c in "{([":
                depth += 1
            elif c in "})]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = text[start:i]
        # only depth-0 keys
        d = 0
        buf = []
        for c in body:
            if c in "{([":
                d += 1
            elif c in "})]":
                d -= 1
            buf.append(c if d == 0 else " ")
        members |= set(re.findall(r"(?:^|[,;\s])(\w+)\s*=(?!=)", "".join(buf)))
    return members


def main() -> int:
    problems = 0
    cache: dict[pathlib.Path, set[str] | None] = {}
    for src in sorted(SCRIPTS.rglob("*.luau")):
        raw = re.sub(r'game:GetService\("(\w+)"\)', r"\1", src.read_text())
        text = clean(raw)
        aliases = {a: e for a, e in ALIAS.findall(raw)}
        for alias, expr in REQ.findall(raw):
            target = resolve(src, expr, aliases)
            if target is None:
                continue
            if not target.exists():
                print(f"{src.relative_to(ROOT)}: require({expr}) -> missing {target.relative_to(ROOT)}")
                problems += 1
                continue
            if target not in cache:
                cache[target] = defined_members(target)
            members = cache[target]
            if members is None:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for mm in re.finditer(rf"(?<![\w.:]){alias}([.:])(\w+)", line):
                    member = mm.group(2)
                    if member in members:
                        continue
                    # assignment of a hook the module leaves open is allowed only if declared
                    print(f"{src.relative_to(ROOT)}:{lineno}: {alias}{mm.group(1)}{member} not defined in {target.relative_to(ROOT)}")
                    problems += 1
    print(f"xref_check: {problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
