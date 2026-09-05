# app/retrieval/filters.py

from qdrant_client.http.models import Filter, FieldCondition, MatchValue, DatetimeRange


def build_qdrant_filter(
    doc_type: str | None = None,
    uploaded_by: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> Filter | None:
    """
    Builds a Qdrant Filter from user-facing retrieval parameters,
    using the payload fields indexed in Phase 3 (doc_type, uploaded_by,
    created_at). Returns None if no filters are given — callers should
    skip passing a filter entirely rather than pass an empty one.
    """
    conditions = []

    if doc_type:
        conditions.append(FieldCondition(key="doc_type", match=MatchValue(value=doc_type)))

    if uploaded_by:
        conditions.append(FieldCondition(key="uploaded_by", match=MatchValue(value=uploaded_by)))

    if created_after or created_before:
        conditions.append(
            FieldCondition(
                key="created_at",
                range=DatetimeRange(gte=created_after, lte=created_before),
            )
        )

    if not conditions:
        return None

    return Filter(must=conditions)