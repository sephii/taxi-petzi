import dataclasses
import datetime
import logging
import os
import re
from typing import Dict, Iterable, List, Tuple

from appdirs import AppDirs
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from taxi.aliases import aliases_database
from taxi.backends import BaseBackend, PushEntryFailed
from taxi.projects import Activity, Project
from taxi.timesheet.entry import Entry

logger = logging.getLogger(__name__)
xdg_dirs = AppDirs("taxi", "sephii")
date_re = re.compile(r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DATES_COL = "B"
DESCRIPTION_COL = "BE"
PROJECTS = {
    "A": (
        "Development",
        {
            "E": ("Website", "petzi_dev_website"),
            "F": ("PeliScan", "petzi_dev_peliscan"),
            "G": ("Other", "petzi_dev_other"),
        },
    ),
    "B": (
        "Infra",
        {
            "O": ("Infra", "petzi_infra"),
        },
    ),
    "C": (
        "Support",
        {
            "V": ("1st level", "petzi_sup_1"),
            "W": ("2nd level", "petzi_sup_2"),
        },
    ),
    "D": (
        "Workgroup",
        {
            "AC": ("Workgroup", "petzi_workgroup"),
        },
    ),
    "E": (
        "Travel",
        {
            "AM": ("Meetings", "petzi_travel_meetings"),
            "AN": ("Other", "petzi_travel_other"),
        },
    ),
    "F": (
        "Misc",
        {
            "AS": ("Admin", "petzi_misc_admin"),
            "AT": ("Other", "petzi_misc_other"),
        },
    ),
}


@dataclasses.dataclass
class EntriesCells:
    durations: Dict[str, float]
    descriptions: Dict[str, List[str]]


class DateNotFound(Exception):
    def __init__(self, date):
        self.date = date


class UnexpectedCellValue(Exception):
    pass


class Spreadsheet:
    def __init__(self, spreadsheet_id: str, credentials_path: str):
        self.spreadsheet_id = spreadsheet_id
        self.credentials_path = credentials_path
        self._service = None

    @property
    def service(self):
        if self._service is not None:
            return self._service

        token_path = os.path.join(xdg_dirs.user_data_dir, "petzi", "token.json")

        creds = (
            Credentials.from_authorized_user_file(token_path, SCOPES)
            if os.path.exists(token_path)
            else None
        )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            if not os.path.exists(os.path.dirname(token_path)):
                os.makedirs(os.path.dirname(token_path))

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        self._service = build("sheets", "v4", credentials=creds).spreadsheets()

        return self._service

    def parse_date(self, date_str):
        match = date_re.match(date_str)

        if match:
            date = match.groupdict()
            return datetime.date(
                year=int(date["year"]), month=int(date["month"]), day=int(date["day"])
            )

        return None

    def unwrap_cell_value(self, value):
        try:
            return value[0][0]
        except IndexError:
            return ""

    def get_dates_rows(self, months: Iterable[int]) -> Dict[datetime.date, int]:
        """
        Return the row number of each date in the given `months`.
        """
        ranges = [f"'{month}'!{DATES_COL}:{DATES_COL}" for month in months]
        result = (
            self.service.values()
            .batchGet(spreadsheetId=self.spreadsheet_id, ranges=ranges)
            .execute()
        )

        dates = {}
        for value_range in result["valueRanges"]:
            for row_number, value in enumerate(value_range["values"], 1):
                if len(value) == 1:
                    date = self.parse_date(value[0])
                    if date:
                        dates[date] = row_number

        return dates

    def get_hours_cell_for_entry(
        self, dates_rows: Dict[datetime.date, int], date: datetime.date, entry: Entry
    ) -> str:
        """
        Return the A1 notation of the duration cell for the given `entry` at the given `date`.
        """
        column = aliases_database[entry.alias].mapping[1]
        try:
            row = dates_rows[date]
        except KeyError:
            raise DateNotFound(date)

        return f"'{date.month}'!{column}{row}"

    def get_description_cell_for_date(
        self, dates_rows: Dict[datetime.date, int], date: datetime.date
    ) -> str:
        """
        Return the A1 notation of the description cell for the given `date`.
        """
        try:
            row = dates_rows[date]
        except KeyError:
            raise DateNotFound(date)

        return f"'{date.month}'!{DESCRIPTION_COL}{row}"

    def get_existing_values(
        self,
        entries_cells: EntriesCells,
    ) -> Dict[str, str]:
        cells = list(
            set(
                list(entries_cells.durations.keys())
                + list(entries_cells.descriptions.keys())
            )
        )
        result = (
            self.service.values()
            .batchGet(spreadsheetId=self.spreadsheet_id, ranges=cells)
            .execute()
        )
        cell_values = {
            cell["range"]: self.unwrap_cell_value(cell.get("values", []))
            for cell in result["valueRanges"]
        }

        return cell_values

    def entries_to_cell_values(
        self,
        entries: List[Tuple[datetime.date, Entry]],
    ) -> EntriesCells:
        duration_cells: Dict[str, float] = {}
        description_cells: Dict[str, List[str]] = {}
        dates_rows = self.get_dates_rows(set(date.month for date, entry in entries))

        for date, entry in entries:
            duration_cell = self.get_hours_cell_for_entry(dates_rows, date, entry)
            if duration_cell not in duration_cells:
                duration_cells[duration_cell] = 0
            duration_cells[duration_cell] += entry.hours

            description_cell = self.get_description_cell_for_date(dates_rows, date)
            if description_cell not in description_cells and entry.description:
                description_cells[description_cell] = []

            if entry.description:
                description_cells[description_cell].append(entry.description)

        return EntriesCells(durations=duration_cells, descriptions=description_cells)

    def merge_existing_entries_with_new(
        self,
        existing_entries: Dict[str, str],
        entries_cells: EntriesCells,
    ) -> Dict[str, str]:
        merged_entries = {}

        for cell, duration in entries_cells.durations.items():
            existing_value_str = existing_entries.get(cell, "")
            try:
                existing_value = float(existing_value_str) if existing_value_str else 0
            except ValueError:
                raise UnexpectedCellValue(
                    f"Error in value of cell {cell}: value '{existing_value_str}' cannot be cast to float."
                )

            merged_entries[cell] = str(existing_value + duration)

        for cell, descriptions in entries_cells.descriptions.items():
            existing_description = existing_entries.get(cell, "")
            descriptions = [
                description
                for description in descriptions
                if description not in existing_description
            ]
            description = ", ".join(descriptions)

            if existing_description:
                description = ", " + description

            merged_entries[cell] = existing_description + description

        return merged_entries

    def write_cells(self, cells: Dict[str, str]):
        self.service.values().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": [
                    {"range": cell, "values": [[value]]}
                    for cell, value in cells.items()
                ],
            },
        ).execute()


class PetziBackend(BaseBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spreadsheet = Spreadsheet(
            spreadsheet_id=kwargs["options"]["sheet_id"],
            credentials_path=kwargs["path"],
        )
        self.entries_to_push = []

    def push_entry(self, date, entry):
        self.entries_to_push.append((date, entry))

    def post_push_entries(self):
        try:
            entries_cell_values = self.spreadsheet.entries_to_cell_values(
                self.entries_to_push
            )
            existing_entries = self.spreadsheet.get_existing_values(entries_cell_values)
            merged = self.spreadsheet.merge_existing_entries_with_new(
                existing_entries, entries_cell_values
            )
            self.spreadsheet.write_cells(merged)
        except DateNotFound as e:
            raise PushEntryFailed(f"Couldn’t find {e.date} date in spreadsheet.")
        except UnexpectedCellValue as e:
            raise PushEntryFailed(str(e))

    def get_projects(self):
        projects_list = []
        for project_id, (project_name, activities) in PROJECTS.items():
            project = Project(project_id, project_name, Project.STATUS_ACTIVE, "")

            for activity_id, (activity_name, alias) in activities.items():
                activity = Activity(activity_id, activity_name)
                project.add_activity(activity)
                project.aliases[alias] = activity_id

            projects_list.append(project)

        return projects_list
