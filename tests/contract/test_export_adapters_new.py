from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from xray_ingest.adapters.confluence_xml import confluence_xml_rows
from xray_ingest.adapters.github_csv import github_csv_rows

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENTITIES_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <hibernate-generic datetime="2025-01-15 10:00:00">
      <object class="Page" package="com.atlassian.confluence.pages">
        <id name="id">123456</id>
        <property name="title"><![CDATA[Architecture Decision Record]]></property>
        <property name="version">3</property>
        <property name="creatorName">jsmith</property>
        <property name="creationDate">2025-01-10 09:15:00.0</property>
        <property name="space">ENG</property>
      </object>
      <object class="Page" package="com.atlassian.confluence.pages">
        <id name="id">123457</id>
        <property name="title"><![CDATA[Sprint Retrospective Notes]]></property>
        <property name="creatorName">alee</property>
        <property name="creationDate">2025-01-14 14:30:00.0</property>
        <property name="space">ENG</property>
      </object>
      <object class="Comment" package="com.atlassian.confluence.pages">
        <id name="id">987654</id>
        <property name="title"><![CDATA[Re: Architecture Decision Record]]></property>
        <property name="creatorName">bwang</property>
        <property name="creationDate">2025-01-11 11:00:00.0</property>
      </object>
    </hibernate-generic>
""")

_ENTITIES_XML_MISSING_CREATOR = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <hibernate-generic datetime="2025-01-15 10:00:00">
      <object class="Page" package="com.atlassian.confluence.pages">
        <id name="id">111</id>
        <property name="title"><![CDATA[Good Page]]></property>
        <property name="creatorName">jsmith</property>
        <property name="creationDate">2025-01-10 09:15:00.0</property>
        <property name="space">ENG</property>
      </object>
      <object class="Page" package="com.atlassian.confluence.pages">
        <id name="id">222</id>
        <property name="title"><![CDATA[Bad Page — no creator]]></property>
        <property name="creationDate">2025-01-11 08:00:00.0</property>
        <property name="space">ENG</property>
      </object>
    </hibernate-generic>
""")

_GITHUB_CSV = textwrap.dedent("""\
    number,title,body,state,created_at,user,labels,milestone,assignee,comments
    1234,Fix authentication bug,"Long body text",open,2025-01-15T10:30:00Z,jsmith,bug;security,,alice,3
    1235,Add dark mode,Short description,closed,2025-01-16T14:00:00Z,bwang,enhancement,,bob,1
""")

_GITHUB_CSV_ALT_HEADERS = textwrap.dedent("""\
    Number,Title,Body,Created At,Author,Labels
    9001,Alternate headers test,Some body,2025-03-01T12:00:00Z,carol,bug
""")


# ---------------------------------------------------------------------------
# Confluence XML tests
# ---------------------------------------------------------------------------

class TestConfluenceXmlRows:
    def test_parses_pages_and_comments(self, tmp_path: Path) -> None:
        xml_file = tmp_path / "entities.xml"
        xml_file.write_text(_ENTITIES_XML, encoding="utf-8")

        rows = confluence_xml_rows(
            xml_file,
            space_modules={"ENG": ("payments-api", "ledger-worker")},
        )

        assert len(rows) == 3
        # Sorted by epoch: page 123456 (Jan 10), comment 987654 (Jan 11), page 123457 (Jan 14)
        page1, comment, page2 = rows

        assert page1["id"] == "123456"
        assert page1["reporter_id"] == "jsmith"
        assert page1["title"] == "Architecture Decision Record"
        assert page1["body"] is None
        assert page1["module_keys"] == ("ledger-worker", "payments-api")
        assert isinstance(page1["occurred_at_epoch"], int)

        assert comment["id"] == "987654"
        assert comment["reporter_id"] == "bwang"
        assert comment["title"] is None
        assert comment["body"] == "Re: Architecture Decision Record"
        assert comment["module_keys"] == ()

        assert page2["id"] == "123457"
        assert page2["reporter_id"] == "alee"

    def test_skips_missing_creator(self, tmp_path: Path) -> None:
        xml_file = tmp_path / "entities.xml"
        xml_file.write_text(_ENTITIES_XML_MISSING_CREATOR, encoding="utf-8")

        rows = confluence_xml_rows(xml_file)

        assert len(rows) == 1
        assert rows[0]["id"] == "111"

    def test_accepts_directory_path(self, tmp_path: Path) -> None:
        (tmp_path / "entities.xml").write_text(_ENTITIES_XML, encoding="utf-8")

        # Pass the directory, not the file directly.
        rows = confluence_xml_rows(tmp_path)

        assert len(rows) == 3

    def test_returns_empty_for_nonexistent_path(self, tmp_path: Path) -> None:
        rows = confluence_xml_rows(tmp_path / "missing.xml")
        assert rows == ()

    def test_returns_empty_for_empty_directory(self, tmp_path: Path) -> None:
        rows = confluence_xml_rows(tmp_path)
        assert rows == ()


# ---------------------------------------------------------------------------
# GitHub CSV tests
# ---------------------------------------------------------------------------

class TestGithubCsvRows:
    def test_parses_standard_export(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "issues.csv"
        csv_file.write_text(_GITHUB_CSV, encoding="utf-8")

        rows = github_csv_rows(
            csv_file,
            repo_module="auth-service",
            label_modules={"security": "security-lib"},
        )

        assert len(rows) == 2
        # Sorted by epoch: issue 1234 (Jan 15), issue 1235 (Jan 16)
        r1, r2 = rows

        assert r1["id"] == "github-issue-1234"
        assert r1["reporter_id"] == "jsmith"
        assert r1["title"] == "Fix authentication bug"
        assert r1["body"] == "Long body text"
        assert "auth-service" in r1["module_keys"]
        assert "security-lib" in r1["module_keys"]
        assert isinstance(r1["occurred_at_epoch"], int)

        assert r2["id"] == "github-issue-1235"
        assert r2["reporter_id"] == "bwang"
        assert "auth-service" in r2["module_keys"]

    def test_maps_labels_to_modules(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "issues.csv"
        csv_file.write_text(_GITHUB_CSV, encoding="utf-8")

        rows = github_csv_rows(
            csv_file,
            label_modules={"bug": "bug-tracker", "security": "security-lib"},
        )

        r1 = rows[0]
        # labels are "bug;security" — both should map
        assert "bug-tracker" in r1["module_keys"]
        assert "security-lib" in r1["module_keys"]

        r2 = rows[1]
        # labels are "enhancement" — no mapping → no label module
        assert r2["module_keys"] == ()

    def test_accepts_alternate_column_names(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "issues.csv"
        csv_file.write_text(_GITHUB_CSV_ALT_HEADERS, encoding="utf-8")

        rows = github_csv_rows(csv_file)

        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == "github-issue-9001"
        assert row["reporter_id"] == "carol"
        assert row["title"] == "Alternate headers test"
        assert isinstance(row["occurred_at_epoch"], int)

    def test_returns_empty_for_header_only_csv(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "issues.csv"
        csv_file.write_text("number,title,created_at,user\n", encoding="utf-8")

        rows = github_csv_rows(csv_file)
        assert rows == ()
