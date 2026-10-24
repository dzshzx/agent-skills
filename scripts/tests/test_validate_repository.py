from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_repository  # noqa: E402


class FrontmatterTest(unittest.TestCase):
    def parse(self, text: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SKILL.md"
            path.write_text(text, encoding="utf-8")
            return validate_repository.frontmatter(path)

    def test_quoted_values_are_unquoted(self):
        fields = self.parse(
            "---\nname: \"demo-skill\"\ndescription: 'Use when: a colon, #hash'\n---\nbody\n"
        )
        self.assertEqual(fields["name"], "demo-skill")
        self.assertEqual(fields["description"], "Use when: a colon, #hash")

    def test_folded_and_literal_scalars_keep_their_text(self):
        fields = self.parse(
            "---\nname: demo\ndescription: >-\n  First line\n  second line.\n"
            "notes: |\n  keep\n  this\n---\n"
        )
        self.assertEqual(fields["description"], "First line second line.")
        self.assertEqual(fields["notes"], "keep this")

    def test_malformed_frontmatter_is_rejected(self):
        for text, message in (
            ("name: demo\n", "must start"),
            ("---\nname: demo\n", "closing delimiter"),
            ("---\nname: [unclosed\n---\n", "invalid YAML"),
        ):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, message):
                    self.parse(text)


class ValidateTest(unittest.TestCase):
    """validate() reports every skill and README problem, in a stable order."""

    def write(self, root: Path, relative: str, text: str = "") -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_validate(self, root: Path) -> list[str]:
        with (
            mock.patch.object(validate_repository, "ROOT", root),
            mock.patch.object(validate_repository, "SKILLS_DIR", root / "skills"),
        ):
            return validate_repository.validate()

    def test_empty_skills_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "skills").mkdir()
            self.write(root, "README.md")
            self.assertEqual(
                self.run_validate(root), ["skills/: no skill directories found"]
            )

    def test_each_problem_is_reported_in_skill_then_readme_order(self):
        home_path = "/" + "home/example/notes"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write(root, "skills/a-missing/notes.txt")
            self.write(root, "skills/b-broken/SKILL.md", "no frontmatter\n")
            self.write(
                root,
                "skills/c-fields/SKILL.md",
                "---\nname: Bad_Name\ndescription:\n---\n"
                f"See {home_path} and [doc](docs/x.md#part) [web](https://e.x) "
                "[mail](mailto:a@e.x) [ok](evals/live-check.sh)\n",
            )
            self.write(root, "skills/c-fields/evals/live-check.sh")
            self.write(
                root,
                "skills/d-good/SKILL.md",
                "---\nname: d-good\ndescription: Use when testing.\n---\n",
            )
            self.write(root, "skills/d-good/evals/live-check.sh")
            self.write(
                root,
                "README.md",
                "[c](skills/c-fields/SKILL.md) [d](skills/d-good/SKILL.md) "
                "[z](skills/z-gone/SKILL.md)\n",
            )
            self.assertEqual(
                self.run_validate(root),
                [
                    "skills/a-missing: missing SKILL.md",
                    "skills/b-broken: missing evals/live-check.sh "
                    "(every skill ships a real-harness check; scripts/verify.sh runs it)",
                    "skills/b-broken/SKILL.md: must start with YAML frontmatter",
                    "skills/c-fields/SKILL.md: name 'Bad_Name' must match directory 'c-fields'",
                    "skills/c-fields/SKILL.md: invalid skill name 'Bad_Name'",
                    "skills/c-fields/SKILL.md: description must not be empty",
                    f"skills/c-fields/SKILL.md: machine-specific home path {'/' + 'home/example'!r}",
                    "skills/c-fields/SKILL.md: missing relative link target 'docs/x.md'",
                    "README.md: missing skill table link for 'a-missing'",
                    "README.md: missing skill table link for 'b-broken'",
                    "README.md: documents nonexistent skill 'z-gone'",
                ],
            )


if __name__ == "__main__":
    unittest.main()
