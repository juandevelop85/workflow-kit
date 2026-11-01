"""T1.2: the kit applies its own workflow to itself."""
import os
import sys
import unittest

from helpers import KIT, run


class Dogfood(unittest.TestCase):
    def test_the_kit_passes_its_own_checker(self):
        script = KIT / ".agents" / "scripts" / "workflow_check.py"
        result = run([sys.executable, str(script), "check", "--commits", "20", "--root", str(KIT)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_core_is_linked_not_copied(self):
        for name in ("agents", "commands", "presets", "scripts", "skills", "templates"):
            self.assertEqual(os.readlink(KIT / ".agents" / name), f"../core/{name}", name)
        self.assertEqual(os.readlink(KIT / ".claude" / "agents"), "../.agents/agents")
        self.assertEqual(os.readlink(KIT / ".claude" / "commands"), "../.agents/commands")
        skills = sorted(p.name for p in (KIT / "core" / "skills").iterdir())
        self.assertEqual(sorted(p.name for p in (KIT / ".claude" / "skills").iterdir()), skills)
        for skill in skills:
            link = KIT / ".claude" / "skills" / skill
            self.assertEqual(os.readlink(link), f"../../.agents/skills/{skill}", skill)
            self.assertTrue((link / "SKILL.md").is_file(), f"{skill}: the link does not resolve")
        for name in ("agents", "commands"):
            self.assertTrue(any((KIT / ".claude" / name).glob("*.md")), f".claude/{name} does not resolve")


if __name__ == "__main__":
    unittest.main()
