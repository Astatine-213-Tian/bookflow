"""Look up a work's Jinjiang page, metadata and official volume/chapter directory.

Read-only: nothing is written. Use it to confirm the official chapter count,
volume boundaries and 番外 chapters before choosing a source or a layout.
"""

from __future__ import annotations

import argparse

from src.cli.output import log, run_command
from src.metadata.catalog import MetadataLookup, PackageMetadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book jjwxc", description=__doc__)
    parser.add_argument("title", help="Work title as listed by the author")
    parser.add_argument("--author", required=True, help="Jinjiang author name")
    args = parser.parse_args(argv)
    return run_command(lambda: lookup(args.title, args.author))


def lookup(title: str, author: str, *, finder: MetadataLookup | None = None) -> dict:
    package = PackageMetadata(title, author, "zh-CN", "", "", "", (), None, None)
    found = (finder or MetadataLookup(kadokado=False)).find(package)
    if found is None or found.provider != "jinjiang":
        raise ValueError(
            f"No unique Jinjiang work titled {title!r} by {author!r}; "
            "check the author name and the title as the author lists it"
        )
    contents = found.table_of_contents
    log(f"{found.title} / {found.author}  {found.source}")
    if contents is None:
        log(f"  directory unavailable: {found.table_of_contents_error}")
    else:
        for volume in contents.volumes:
            first, last = volume.chapters[0], volume.chapters[-1]
            log(
                f"  [{volume.title or '(no volume)'}] {first.number}-{last.number}: "
                f"{first.title} … {last.title}"
            )
    return {
        "source": found.source,
        "title": found.title,
        "author": found.author,
        "date": found.date,
        "subjects": list(found.subjects),
        "table_of_contents": contents.to_dict() if contents else None,
        "table_of_contents_error": found.table_of_contents_error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
