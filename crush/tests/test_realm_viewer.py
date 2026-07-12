# SPDX-License-Identifier: Apache-2.0
"""Tests for the Realm viewer's Views-tab link resolution (no Qt required)."""
from __future__ import annotations

import sqlite3

from crush.viewers.realm_viewer import _build_resolved_view, _create_realm_sqlite


def _participant_table() -> dict:
    # class_MessageParticipantLocalDto-shaped: obj_keys [10, 20, 30]
    return {
        "column_names": ["id", "email", "name"],
        "column_types": ["string", "string", "string"],
        "columns": {
            0: ["p10", "p20", "p30"],
            1: ["a@x.com", "b@x.com", "c@x.com"],
            2: ["Alice", "", "Carol"],
        },
        "obj_keys": [10, 20, 30],
        "row_count": 3,
    }


def _attachment_table() -> dict:
    return {
        "column_names": ["id", "name", "size"],
        "column_types": ["string", "string", "int"],
        "columns": {
            0: ["a1", "a2"],
            1: ["invoice.pdf", "photo.jpg"],
            2: [1024, 2048],
        },
        "obj_keys": [100, 200],
        "row_count": 2,
    }


def test_build_resolved_view_single_link_expands_into_own_columns() -> None:
    """A to-one Link's selected columns land in their own named columns
    (prefixed with the link column's name) instead of one flattened text
    cell -- the fix for a real-world table (Realm's MessageLocalDto ->
    MessageAttributesLocalDto, 25 columns) where cramming everything into
    one cell made the result unreadable."""
    source = {
        "column_names": ["subject", "sender"],
        "column_types": ["string", "link"],
        "columns": {0: ["Hello", "Bye"], 1: [10, 30]},
        "obj_keys": [1, 2],
        "row_count": 2,
    }
    result = _build_resolved_view(source, [("sender", _participant_table(), ["email"], [])])
    assert result["columns"] == ["subject", "sender.email"]
    assert result["rows"] == [
        ["Hello", "a@x.com"],
        ["Bye", "c@x.com"],
    ]
    assert result["__obj_keys"] == [1, 2]


def test_build_resolved_view_single_link_multiple_selected_columns() -> None:
    source = {
        "column_names": ["subject", "sender"],
        "column_types": ["string", "link"],
        "columns": {0: ["Hello"], 1: [20]},
        "obj_keys": [1],
        "row_count": 1,
    }
    result = _build_resolved_view(
        source, [("sender", _participant_table(), ["name", "email"], [])]
    )
    assert result["columns"] == ["subject", "sender.name", "sender.email"]
    # name is empty for objkey 20 -- selected columns are shown as-is, no
    # guessing/fallback here (that heuristic-avoidance was the whole point).
    assert result["rows"] == [["Hello", "", "b@x.com"]]


def test_build_resolved_view_linklist_joins_multiple_targets() -> None:
    source = {
        "column_names": ["subject", "recipients"],
        "column_types": ["string", "linklist"],
        "columns": {0: ["Meeting"], 1: [[10, 30]]},
        "obj_keys": [5],
        "row_count": 1,
    }
    result = _build_resolved_view(source, [("recipients", _participant_table(), ["email"], [])])
    # A to-many LinkList can't become a fixed set of columns (variable
    # number of targets per row), so it stays one flattened text cell.
    assert result["columns"] == ["subject", "recipients"]
    assert result["rows"] == [["Meeting", "email=a@x.com; email=c@x.com"]]


def test_build_resolved_view_empty_linklist_and_unresolved_link_become_none() -> None:
    source = {
        "column_names": ["subject", "recipients", "sender"],
        "column_types": ["string", "linklist", "link"],
        "columns": {0: ["No one"], 1: [[]], 2: [None]},
        "obj_keys": [9],
        "row_count": 1,
    }
    result = _build_resolved_view(source, [("recipients", _participant_table(), ["email"], [])])
    assert result["rows"] == [["No one", None, None]]


def test_build_resolved_view_resolves_multiple_link_columns_in_one_pass() -> None:
    """A table with several Link/LinkList columns (e.g. class_MessageAttributesLocalDto's
    from/to/attachments) can be resolved together in one call, each against
    its own target table and column selection -- the scenario that needed
    one tab per column before. The to-one "from" expands into its own
    column; the to-many "attachments" stays collapsed."""
    source = {
        "column_names": ["subject", "from", "attachments"],
        "column_types": ["string", "link", "linklist"],
        "columns": {
            0: ["Invoice"],
            1: [10],
            2: [[100, 200]],
        },
        "obj_keys": [1],
        "row_count": 1,
    }
    result = _build_resolved_view(
        source,
        [
            ("from", _participant_table(), ["email"], []),
            ("attachments", _attachment_table(), ["name"], []),
        ],
    )
    assert result["columns"] == ["subject", "from.email", "attachments"]
    assert result["rows"] == [
        ["Invoice", "a@x.com", "name=invoice.pdf; name=photo.jpg"]
    ]


def test_build_resolved_view_link_column_not_configured_stays_raw() -> None:
    """Only the configured link columns are touched -- others (e.g. because
    the user left that group's checklist empty) keep their raw value."""
    source = {
        "column_names": ["subject", "from", "attachments"],
        "column_types": ["string", "link", "linklist"],
        "columns": {0: ["Invoice"], 1: [10], 2: [[100]]},
        "obj_keys": [1],
        "row_count": 1,
    }
    result = _build_resolved_view(source, [("from", _participant_table(), ["email"], [])])
    assert result["columns"] == ["subject", "from.email", "attachments"]
    assert result["rows"] == [["Invoice", "a@x.com", [100]]]


def test_build_resolved_view_resolves_nested_link_under_linklist_two_hops() -> None:
    """A selected target column that's itself a Link/LinkList can be resolved
    one hop further via a nested LinkConfig -- the multi-table chain (e.g.
    message -> attachment -> uploader) the flat single-hop version couldn't
    reach. Nested under a to-many LinkList, the whole subtree stays one
    flattened text cell (can't become columns without row multiplication)."""
    source = {
        "column_names": ["subject", "attachments"],
        "column_types": ["string", "linklist"],
        "columns": {0: ["Invoice"], 1: [[100, 200]]},
        "obj_keys": [1],
        "row_count": 1,
    }
    attachment_with_uploader = {
        "column_names": ["id", "name", "size", "uploader"],
        "column_types": ["string", "string", "int", "link"],
        "columns": {
            0: ["a1", "a2"],
            1: ["invoice.pdf", "photo.jpg"],
            2: [1024, 2048],
            3: [10, 30],
        },
        "obj_keys": [100, 200],
        "row_count": 2,
    }
    result = _build_resolved_view(
        source,
        [
            (
                "attachments",
                attachment_with_uploader,
                ["name"],
                [("uploader", _participant_table(), ["email"], [])],
            ),
        ],
    )
    assert result["columns"] == ["subject", "attachments"]
    assert result["rows"] == [
        [
            "Invoice",
            "name=invoice.pdf, uploader=[email=a@x.com]; "
            "name=photo.jpg, uploader=[email=c@x.com]",
        ]
    ]


def test_build_resolved_view_resolves_nested_link_under_link_expands_columns() -> None:
    """The MessageLocalDto -> MessageAttributesLocalDto -> SpamInfoLocalDto
    real-world shape: a to-one Link nested inside another to-one Link
    expands into its own doubly-prefixed column, not text, since neither
    hop is to-many."""
    source = {
        "column_names": ["subject", "messageAttributes"],
        "column_types": ["string", "link"],
        "columns": {0: ["Invoice"], 1: [500]},
        "obj_keys": [1],
        "row_count": 1,
    }
    attrs_table = {
        "column_names": ["content", "spamInfo"],
        "column_types": ["string", "link"],
        "columns": {0: ["Please pay"], 1: [900]},
        "obj_keys": [500],
        "row_count": 1,
    }
    spam_table = {
        "column_names": ["reason"],
        "column_types": ["string"],
        "columns": {0: ["none"]},
        "obj_keys": [900],
        "row_count": 1,
    }
    result = _build_resolved_view(
        source,
        [
            (
                "messageAttributes",
                attrs_table,
                ["content"],
                [("spamInfo", spam_table, ["reason"], [])],
            ),
        ],
    )
    assert result["columns"] == [
        "subject",
        "messageAttributes.content",
        "messageAttributes.spamInfo.reason",
    ]
    assert result["rows"] == [["Invoice", "Please pay", "none"]]


def test_build_resolved_view_nested_link_not_configured_stays_unresolved() -> None:
    """A selected target column that's itself a link, but with no nested
    LinkConfig supplied, is shown as-is (the raw ObjKey) -- matching the
    existing "unchecked = leave raw" convention one level deeper. Nested
    under a top-level LinkList, so still a single flattened text cell."""
    source = {
        "column_names": ["subject", "attachments"],
        "column_types": ["string", "linklist"],
        "columns": {0: ["Invoice"], 1: [[100]]},
        "obj_keys": [1],
        "row_count": 1,
    }
    attachment_with_uploader = {
        "column_names": ["id", "name", "uploader"],
        "column_types": ["string", "string", "link"],
        "columns": {0: ["a1"], 1: ["invoice.pdf"], 2: [10]},
        "obj_keys": [100],
        "row_count": 1,
    }
    result = _build_resolved_view(
        source,
        [("attachments", attachment_with_uploader, ["name", "uploader"], [])],
    )
    assert result["columns"] == ["subject", "attachments"]
    assert result["rows"] == [["Invoice", "name=invoice.pdf, uploader=10"]]


def test_resolved_view_can_be_backed_by_a_queryable_sqlite_file() -> None:
    """A Views-tab result opens as a new tab backed by a temp SQLite file
    (_create_realm_sqlite, reused as-is since it already accepts this
    {"columns", "rows", "__obj_keys"} shape) so that tab's own SQL box can
    pick/reorder a subset of the resolved columns for display/export --
    without touching the Views tab's configuration or any other open tab.
    Dotted column names from an expanded to-one Link (e.g.
    "messageAttributes.subject") must survive as quoted SQL identifiers."""
    source = {
        "column_names": ["subject", "messageAttributes"],
        "column_types": ["string", "link"],
        "columns": {0: ["Invoice", "Reminder"], 1: [500, 600]},
        "obj_keys": [1, 2],
        "row_count": 2,
    }
    attrs_table = {
        "column_names": ["content", "isUnread"],
        "column_types": ["string", "bool"],
        "columns": {0: ["Please pay", "Second notice"], 1: [False, True]},
        "obj_keys": [500, 600],
        "row_count": 2,
    }
    resolved = _build_resolved_view(
        source, [("messageAttributes", attrs_table, ["content", "isUnread"], [])]
    )
    assert resolved["columns"] == [
        "subject",
        "messageAttributes.content",
        "messageAttributes.isUnread",
    ]

    tmp = _create_realm_sqlite({"class_MessageLocalDto (messageAttributes)": resolved})
    assert tmp is not None
    try:
        conn = sqlite3.connect(str(tmp))
        rows = conn.execute(
            'SELECT "messageAttributes.content" '
            'FROM "class_MessageLocalDto (messageAttributes)" '
            'WHERE "messageAttributes.isUnread" = 1'
        ).fetchall()
        conn.close()
        assert rows == [("Second notice",)]
    finally:
        tmp.unlink(missing_ok=True)
