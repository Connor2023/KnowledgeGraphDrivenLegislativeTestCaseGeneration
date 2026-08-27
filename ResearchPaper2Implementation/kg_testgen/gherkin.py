"""Minimal Gherkin reader for the feature files this pipeline generates.

Not a general Gherkin parser -- it handles the subset the generator emits: one Feature,
tagged Scenarios, a `# Derives from:` provenance comment, and Given/When/Then/And/But
steps. Enough to hand each scenario to a policy judge as a self-contained unit.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import List, Optional

STEP_KEYWORDS = ("Given ", "When ", "Then ", "And ", "But ")
DERIVES_RE = re.compile(r"^#\s*Derives from:\s*(.+)$", re.IGNORECASE)


@dataclass
class Scenario:
    name: str
    tags: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    derives_from: Optional[str] = None
    line_number: int = 0

    @property
    def provision_tag(self) -> Optional[str]:
        """The @sN-M tag identifying the source provision, if present."""
        for tag in self.tags:
            if re.fullmatch(r"@s\d+(-\d+)?", tag):
                return tag
        return None

    def as_text(self) -> str:
        lines = []
        if self.tags:
            lines.append(" ".join(self.tags))
        lines.append("Scenario: %s" % self.name)
        if self.derives_from:
            lines.append("  Derives from: %s" % self.derives_from)
        lines.extend("  %s" % s for s in self.steps)
        return "\n".join(lines)

    def assertion_steps(self) -> List[str]:
        """The Then/And-after-Then steps -- what the policy is actually judged against."""
        out, in_then = [], False
        for step in self.steps:
            if step.startswith("Then "):
                in_then, _ = True, out.append(step)
            elif in_then and step.startswith(("And ", "But ")):
                out.append(step)
            elif step.startswith(("Given ", "When ")):
                in_then = False
        return out

    def as_dict(self) -> dict:
        return {"name": self.name, "tags": self.tags, "steps": self.steps,
                "derives_from": self.derives_from, "line_number": self.line_number}


@dataclass
class Feature:
    name: str = ""
    scenarios: List[Scenario] = field(default_factory=list)
    path: Optional[str] = None


def parse_feature(path: str) -> Feature:
    with io.open(path, encoding="utf-8") as fh:
        return parse_feature_text(fh.read(), path=path)


def parse_feature_text(text: str, path: Optional[str] = None) -> Feature:
    feature = Feature(path=path)
    pending_tags: List[str] = []
    current: Optional[Scenario] = None

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue

        if line.startswith("Feature:"):
            feature.name = line[len("Feature:"):].strip()
            pending_tags = []
            continue

        if line.startswith("@"):
            pending_tags = [t for t in line.split() if t.startswith("@")]
            continue

        if line.startswith(("Scenario:", "Scenario Outline:")):
            current = Scenario(
                name=line.split(":", 1)[1].strip(),
                tags=pending_tags,
                line_number=number,
            )
            feature.scenarios.append(current)
            pending_tags = []
            continue

        if current is None:
            continue

        match = DERIVES_RE.match(line)
        if match:
            current.derives_from = match.group(1).strip().strip('"')
            continue

        if line.startswith("#"):
            continue

        if line.startswith(STEP_KEYWORDS):
            current.steps.append(line)

    return feature
