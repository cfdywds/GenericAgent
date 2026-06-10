"""Ensure PALETTE_ENTRIES in slash_cmds.py are documented in README.md.

This prevents the command reference table from silently falling behind
the actual command palette after future refactors.
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
README = REPO / "README.md"


def test_palette_entries_appear_in_readme():
    readme_text = README.read_text(encoding="utf-8").lower()
    src = (REPO / "frontends" / "slash_cmds.py").read_text(encoding="utf-8")

    # Extract PALETTE_ENTRIES command names
    import re
    palette = re.findall(r'"/(\w+)"', src.split("PALETTE_ENTRIES")[1].split("]")[0])
    missing = [cmd for cmd in palette if f"/{cmd}" not in readme_text]
    assert not missing, (
        f"These slash commands are in PALETTE_ENTRIES but not in README.md: {missing}"
    )
