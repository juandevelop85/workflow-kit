"""Acceptance criteria 1 and 6, and structural checks on the prose of the core.

1. The core never names a product.
6. The method documentation contains no product-specific decisions.
"""
import pathlib
import py_compile
import re
import unittest

from helpers import KIT

# Built from pieces so that this very file does not contain the forbidden word.
FORBIDDEN = "ant" + "os"
SKIP_DIRS = {".git", "__pycache__"}


def text_files(root: pathlib.Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not (set(path.relative_to(root).parts) & SKIP_DIRS) and path.suffix != ".pyc":
            yield path


def frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path}: no frontmatter"
    out, key = {}, None
    for line in match.group(1).splitlines():
        m = re.match(r"^([a-z-]+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            out[key] = m.group(2).strip().lstrip(">-").strip()
        elif key and line.startswith("  "):
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


class NoProductInTheKit(unittest.TestCase):
    def test_no_file_of_the_kit_names_a_product(self):
        offenders = [
            p.relative_to(KIT).as_posix()
            for p in text_files(KIT)
            if FORBIDDEN in p.read_text(encoding="utf-8", errors="ignore").lower()
            or FORBIDDEN in p.name.lower()
        ]
        self.assertEqual(offenders, [])

    def test_the_method_and_adoption_docs_are_free_of_product_decisions(self):
        for name in ("method.md", "adoption.md", "configuration.md"):
            text = (KIT / "docs" / name).read_text(encoding="utf-8").lower()
            self.assertNotIn(FORBIDDEN, text, name)


class CoreStructure(unittest.TestCase):
    def test_scripts_compile(self):
        for path in list((KIT / "core/scripts").glob("*.py")) + [KIT / "install.py"]:
            py_compile.compile(str(path), doraise=True)

    def test_every_skill_agent_and_command_has_valid_frontmatter(self):
        for skill in sorted((KIT / "core/skills").iterdir()):
            fm = frontmatter(skill / "SKILL.md")
            self.assertEqual(fm.get("name"), skill.name)
            self.assertTrue(fm.get("description"), skill.name)
        for agent in sorted((KIT / "core/agents").glob("*.md")):
            fm = frontmatter(agent)
            self.assertEqual(fm.get("name"), agent.stem)
            self.assertTrue(fm.get("description"), agent.name)
            self.assertIn("Read", fm.get("tools", ""), agent.name)
            self.assertNotIn("Edit", fm.get("tools", ""), f"{agent.name} must be read-only")
            self.assertNotIn("Write", fm.get("tools", ""), f"{agent.name} must be read-only")
        for command in sorted((KIT / "core/commands").glob("*.md")):
            self.assertTrue(frontmatter(command).get("description"), command.name)

    def test_names_referenced_in_the_prose_exist(self):
        skills = {p.name for p in (KIT / "core/skills").iterdir()}
        agents = {p.stem for p in (KIT / "core/agents").glob("*.md")}
        commands = {p.stem for p in (KIT / "core/commands").glob("*.md")}
        corpus = "\n".join(p.read_text(encoding="utf-8") for p in text_files(KIT / "core") if p.suffix == ".md")
        for ref in set(re.findall(r"`(/[a-z-]+)", corpus)):
            self.assertIn(ref.lstrip("/"), commands, f"command {ref} is referenced but does not exist")
        for name in skills | agents:
            self.assertIn(name, corpus, f"{name} is never referenced")

    def test_prose_points_only_at_scripts_and_templates_that_exist(self):
        corpus = "\n".join(p.read_text(encoding="utf-8") for p in text_files(KIT / "core") if p.suffix in {".md", ".tmpl"})
        for ref in set(re.findall(r"\.agents/(scripts|templates|presets)/([A-Za-z0-9_.-]+)", corpus)):
            folder, name = ref
            self.assertTrue((KIT / "core" / folder / name).exists(), f".agents/{folder}/{name} does not exist")

    def test_the_reviewers_say_they_are_read_only(self):
        # the tool list is checked above; the prose must say it too, so a reader (or a
        # future edit of the tool list) is not surprised
        for agent in (KIT / "core/agents").glob("*.md"):
            self.assertIn("Read-only", agent.read_text(encoding="utf-8"), agent.name)


if __name__ == "__main__":
    unittest.main()
