import datetime
from unittest.mock import call, patch

import pytest
import taxi.aliases
from taxi.aliases import Mapping
from taxi.backends import PushEntryFailed
from taxi.projects import ProjectsDb
from taxi.timesheet.entry import Entry
from taxi.ui.tty import TtyUi

from taxi_petzi.backend import DESCRIPTION_COL, PetziBackend, Spreadsheet


@pytest.fixture
def aliases_database():
    taxi.aliases.aliases_database.reset()
    taxi.aliases.aliases_database["petzi_dev_website"] = Mapping(
        mapping=("A", "A"), backend="local"
    )

    yield taxi.aliases.aliases_database


@pytest.fixture
def backend(aliases_database, tmp_path):
    projects_db_path = str(tmp_path / "projects.json")
    yield PetziBackend(
        options={"sheet_id": "1"},
        username="",
        password="",
        hostname="",
        port=None,
        path="/dev/null",
        context={"view": TtyUi(), "projects_db": ProjectsDb(projects_db_path)},
    )


def test_push_entry_with_date_not_in_spreadsheet_raises_error(backend):
    entry = Entry(alias="petzi_dev_website", duration=1, description="")

    with patch.object(Spreadsheet, "get_dates_rows") as get_dates_rows:
        get_dates_rows.return_value = {datetime.date(2014, 1, 1): 1}
        backend.push_entry(datetime.date(2015, 1, 1), entry)

        with pytest.raises(PushEntryFailed):
            backend.post_push_entries()


def test_push_entry_with_unexpected_existing_duration_raises_error(backend):
    entry = Entry(alias="petzi_dev_website", duration=1, description="")

    with patch.object(
        Spreadsheet, "get_existing_values"
    ) as get_existing_values, patch.object(
        Spreadsheet, "get_dates_rows"
    ) as get_dates_rows:
        get_dates_rows.return_value = {datetime.date(2015, 1, 1): 1}
        get_existing_values.return_value = {"'1'!A1": "foobar"}
        backend.push_entry(datetime.date(2015, 1, 1), entry)

        with pytest.raises(PushEntryFailed):
            backend.post_push_entries()


def test_push_entry_merges_it_with_existing_values(backend):
    entry = Entry(alias="petzi_dev_website", duration=1, description="hello")

    with patch.object(
        Spreadsheet, "get_existing_values"
    ) as get_existing_values, patch.object(
        Spreadsheet, "get_dates_rows"
    ) as get_dates_rows, patch.object(
        Spreadsheet, "write_cells"
    ) as write_cells:
        get_dates_rows.return_value = {datetime.date(2015, 1, 1): 1}
        get_existing_values.return_value = {
            "'1'!A1": "2.5",
            f"'1'!{DESCRIPTION_COL}1": "existing value",
        }
        backend.push_entry(datetime.date(2015, 1, 1), entry)
        backend.post_push_entries()

        assert write_cells.call_args_list == [
            call({"'1'!A1": "3.5", f"'1'!{DESCRIPTION_COL}1": "existing value, hello"})
        ]


def test_multiple_entries_on_same_date_merges_them(backend):
    entries = [
        Entry(alias="petzi_dev_website", duration=1, description="hello"),
        Entry(alias="petzi_dev_website", duration=2, description="foobar"),
    ]

    with patch.object(
        Spreadsheet, "get_existing_values"
    ) as get_existing_values, patch.object(
        Spreadsheet, "get_dates_rows"
    ) as get_dates_rows, patch.object(
        Spreadsheet, "write_cells"
    ) as write_cells:
        get_dates_rows.return_value = {datetime.date(2015, 1, 1): 1}
        get_existing_values.return_value = {}
        for entry in entries:
            backend.push_entry(datetime.date(2015, 1, 1), entry)

        backend.post_push_entries()

        assert write_cells.call_args_list == [
            call({"'1'!A1": "3", f"'1'!{DESCRIPTION_COL}1": "hello, foobar"})
        ]
