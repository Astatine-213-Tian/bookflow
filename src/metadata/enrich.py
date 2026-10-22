"""Resolve official book metadata before creating an editable source."""

from __future__ import annotations

from src.metadata.catalog import MetadataLookup, PackageMetadata

# `series` covers the series name and position; `volumes` applies the official
# volume titles, which only a local edition's reviewed outline can take.
METADATA_FIELDS = (
    "title",
    "language",
    "date",
    "source",
    "description",
    "subjects",
    "series",
)
ENRICH_FIELDS = METADATA_FIELDS + ("volumes",)


def parse_enrich_fields(
    value: str, *, allowed: tuple[str, ...] = ENRICH_FIELDS
) -> frozenset[str]:
    """Parse `all` or a comma-separated subset of the allowed fields."""
    names = [name.strip() for name in value.split(",") if name.strip()]
    if names == ["all"]:
        return frozenset(allowed)
    unknown = sorted(set(names) - set(allowed))
    if not names or unknown:
        raise ValueError(
            "Enrichment fields must be all or a comma-separated subset of "
            + ", ".join(allowed)
            + (f"; unknown: {', '.join(unknown)}" if unknown else "")
        )
    return frozenset(names)


def enrich_source(
    book: dict,
    *,
    fields: frozenset[str] = frozenset(METADATA_FIELDS),
    lookup: MetadataLookup | None = None,
    keep: frozenset[str] = frozenset(),
) -> dict:
    """Replace selected fields with the authoritative match.

    ``keep`` names explicit user overrides. The local title can name a revised
    edition, so it is only filled when missing; an empty match never erases a value.
    """
    data = book["metadata"]
    package = PackageMetadata(
        title=data["title"],
        author=data["creator"],
        language=data["language"],
        date=data["date"],
        source=data["source"],
        description=data["description"],
        subjects=tuple(data["subjects"]),
        series=data["series"] or None,
        series_position=str(data["series_position"])
        if data["series_position"]
        else None,
    )
    source = (lookup or MetadataLookup()).find(package, primary_subject="")
    if source is None:
        return {"status": "unmatched"}
    candidates = {
        "title": source.title,
        "language": source.language,
        "date": source.date,
        "source": source.source,
        "description": source.description,
        "subjects": list(source.subjects),
    }
    if source.series_verified:
        candidates.update(
            series=source.series or "", series_position=source.series_position or ""
        )
    for key, value in candidates.items():
        field = "series" if key == "series_position" else key
        if field not in fields or field in keep:
            continue
        if key == "title" and data.get(key):
            continue
        if value or not data.get(key):
            data[key] = value
    return {
        "status": "matched",
        "provider": source.provider,
        "url": source.source,
        "table_of_contents": source.table_of_contents.to_dict()
        if source.table_of_contents is not None
        else None,
        "table_of_contents_error": source.table_of_contents_error,
    }
