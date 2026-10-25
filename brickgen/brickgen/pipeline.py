"""Build a draft with LDraw Nova: plan, recolour, review (build + checks + renders), GLB.

LDraw Nova is used only through its command line, from its own checkout and
virtual environment. Nothing here writes into that checkout.
"""
from __future__ import annotations

import csv
import functools
import json
import logging
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from . import generators
from .catalog import COLOURS, TEMPLATES, Template
from .config import Settings
from .planner import Draft

log = logging.getLogger(__name__)

# Files a visitor can download, by public name -> path inside the job folder.
FILES = {
    "model.mpd": "review/model.mpd",
    "model.glb": "model.glb",
    "model.plan.json": "model.plan.json",
    "parts.csv": "parts.csv",
    "preview.png": "review/previews/home.png",
    "front.png": "review/previews/front.png",
    "top.png": "review/previews/top.png",
    "review.json": "review/review.json",
    "validation.json": "review/validation.json",
}

STAGE_CHECKS = {
    "validation": "Файл и геометрия: настоящие детали LDraw, корпуса кубиков не пересекаются",
    "bom": "Список деталей посчитан",
    "render": "LeoCAD открыл модель и отрисовал её",
    "bom_comparison": "Списки деталей LeoCAD и проверки совпадают",
}

DIAGNOSTICS = {
    "assembly.disconnected_evidence": (
        "Анализ соединений видит {component_count} отдельных групп деталей. Так бывает с намеренно "
        "отдельными объектами (дерево, подставка) и с соединениями, которые проверка не распознаёт."),
    "coverage.collision_review": (
        "Не для всех деталей есть точная проверка пересечений; спорные места оставлены для осмотра."),
    "part.alias_or_internal": "Деталь-псевдоним: лучше заменить её актуальным номером.",
    "assembly.body_overlap": "Корпуса кубиков пересекаются: так собрать нельзя.",
    "assembly.duplicate": "Одна и та же деталь стоит дважды в одном месте.",
    "geometry.incomplete": "Геометрия части деталей не загрузилась, проверка неполная.",
}


class _Missing(dict):
    def __missing__(self, key):
        return "?"


class NovaError(RuntimeError):
    """LDraw Nova could not produce the model."""


def _tail(text: str, limit: int = 1500) -> str:
    return text[-limit:].strip()


class Nova:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.agent = settings.nova_dir / "ldraw-agent"

    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
        env["LDRAW_DIR"] = str(self.settings.ldraw_dir)
        env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        if self.settings.extra_path:
            env["PATH"] = self.settings.extra_path + os.pathsep + env.get("PATH", "")
        return env

    def run(self, *args, cwd: Path, timeout: int = 120, display: bool = False) -> subprocess.CompletedProcess:
        command = [str(self.agent), "--library", str(self.settings.ldraw_dir), *map(str, args)]
        if display and self.settings.xvfb:
            command = ["xvfb-run", "-a", *command]
        log.info("run %s", " ".join(command))
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=self.env(), cwd=cwd)

    def status(self) -> dict[str, bool]:
        path = self.env()["PATH"]
        return {
            "ldraw_nova": self.agent.exists() and (self.settings.nova_dir / ".venv" / "bin" / "python").exists(),
            "parts_library": (self.settings.ldraw_dir / "LDConfig.ldr").exists(),
            "leocad": shutil.which("leocad", path=path) is not None,
            "mpd2glb": shutil.which("mpd2glb.sh", path=path) is not None,
            "xvfb": not self.settings.xvfb or shutil.which("xvfb-run", path=path) is not None,
        }

    @functools.cached_property
    def palettes(self) -> dict:
        proc = self.run("design", "palettes", cwd=self.settings.data_dir, timeout=60)
        if proc.returncode:
            raise NovaError("Не удалось прочитать палитры LDraw Nova: " + _tail(proc.stderr))
        return json.loads(proc.stdout)

    @functools.cached_property
    def colour_codes(self) -> dict[str, int]:
        codes = {}
        pattern = re.compile(r"0\s+!COLOUR\s+(\S+)\s+CODE\s+(\d+)")
        with open(self.settings.ldraw_dir / "LDConfig.ldr", encoding="utf-8", errors="replace") as f:
            for line in f:
                if m := pattern.match(line):
                    codes[m.group(1)] = int(m.group(2))
        return codes


def recolour(plan: dict, rules: list[tuple[str | int, str, tuple[str, ...]]], codes: dict[str, int]) -> int:
    """Replace colours in place; each rule is (source colour, new colour, sections or ())."""

    def key(colour):
        if isinstance(colour, str) and colour.startswith("@colours."):
            return codes.get(colour.removeprefix("@colours."), colour)
        return colour

    rules = [(key(src), dst, sections) for src, dst, sections in rules]
    changed = 0
    for section in plan["sections"]:
        for step in section["steps"]:
            for placement in step:
                current = key(placement["colour"])
                for src, dst, sections in rules:
                    if current == src and (not sections or section["name"] in sections):
                        placement["colour"] = dst
                        changed += 1
                        break
    return changed


class Builder:
    def __init__(self, settings: Settings, nova: Nova | None = None):
        self.settings = settings
        self.nova = nova or Nova(settings)

    def make_plan(self, draft: Draft, workdir: Path) -> Path:
        template: Template = TEMPLATES[draft.template]
        rules = []
        if template.kind == "vehicle":
            palette = draft.palette or template.default_palette
            source = workdir / "source.plan.json"
            proc = self.nova.run("vehicle", "plan", template.source, "--palette", palette,
                                 "--output", source, "--force", cwd=workdir)
            if proc.returncode or not source.exists():
                raise NovaError("LDraw Nova не выдал план машины: " + _tail(proc.stderr or proc.stdout))
            plan = json.loads(source.read_text(encoding="utf-8"))
            roles = self.nova.palettes[palette]["roles"]
            rules = [(roles[template.role(role).source], f"@colours.{colour}", ()) for role, colour in draft.colours.items()]
        elif template.kind == "example":
            plan = json.loads((self.settings.nova_dir / template.source).read_text(encoding="utf-8"))
            rules = [(template.role(role).source, f"@colours.{colour}", template.role(role).sections)
                     for role, colour in draft.colours.items()]
        else:
            plan = generators.build(template.source, draft.colours)
        changed = recolour(plan, rules, self.nova.colour_codes) if rules else 0
        if template.attribution:
            plan["license"] = template.attribution + ("; recoloured by BrickGen" if changed else "")
        path = workdir / "model.plan.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def review(self, workdir: Path) -> dict:
        outdir = workdir / "review"
        proc = self.nova.run("review", workdir / "model.plan.json", "--outdir", outdir, "--force",
                             cwd=workdir, timeout=self.settings.review_timeout, display=True)
        report = outdir / "review.json"
        if not report.exists():
            raise NovaError("Проверка LDraw Nova не запустилась: " + _tail(proc.stderr or proc.stdout))
        return json.loads(report.read_text(encoding="utf-8"))

    def glb(self, workdir: Path) -> str | None:
        """Convert the reviewed MPD for the 3D viewer; returns an error text instead of raising."""
        proc = self.nova.run("glb", workdir / "review" / "model.mpd", "--output", workdir / "model.glb",
                             "--timeout", self.settings.glb_timeout, cwd=workdir, timeout=self.settings.glb_timeout + 30)
        if proc.returncode or not (workdir / "model.glb").exists():
            return _tail(proc.stderr or proc.stdout, 600) or "mpd2glb не создал файл"
        return None

    def collect(self, workdir: Path, review: dict, glb_error: str | None) -> dict:
        bom = []
        bom_path = workdir / "review" / "bom.json"
        if bom_path.exists():
            hexes = {c.name: c.hex for c in COLOURS.values()}
            for row in json.loads(bom_path.read_text(encoding="utf-8"))["bom"]:
                bom.append(dict(part=row["part"], description=" ".join(row["description"].split()),
                                colour=row["colour_name"], code=row["colour_code"],
                                hex=hexes.get(row["colour_name"]), quantity=row["quantity"]))
            with open(workdir / "parts.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["part", "description", "colour", "colour_code", "quantity"])
                for row in bom:
                    writer.writerow([row["part"], row["description"], row["colour"], row["code"], row["quantity"]])
        counts = Counter(d["code"] for d in review.get("diagnostics", []))
        notes, seen = [], set()
        for d in review.get("diagnostics", []):
            if d["code"] in seen:
                continue
            seen.add(d["code"])
            text = DIAGNOSTICS.get(d["code"], d["message"]).format_map(_Missing(d))
            notes.append(dict(code=d["code"], severity=d["severity"], count=counts[d["code"]], text=text))
        files = sorted(name for name, rel in FILES.items() if (workdir / rel).exists())
        return dict(
            checks=dict(passed=bool(review.get("checks_passed")),
                        stages=[dict(key=k, label=STAGE_CHECKS.get(k, k), status=v)
                                for k, v in review.get("stages", {}).items()],
                        notes=notes, physical_validity=review.get("physical_validity")),
            placements=review.get("physical_placements"),
            part_types=len(bom),
            bom=bom,
            files=files,
            glb_error=glb_error,
        )
