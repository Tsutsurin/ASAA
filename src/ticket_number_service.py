import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger('auto_responsible.ticket_number')


NUMBER_RE = re.compile(r'^\d+$')


def get_max_ticket_number(tasks_dir: Path) -> int:
    tasks_dir.mkdir(parents=True, exist_ok=True)

    numbers = []

    for item in tasks_dir.iterdir():
        if not item.is_dir():
            continue

        name = item.name.strip()

        if NUMBER_RE.match(name):
            numbers.append(int(name))

    if not numbers:
        return 0

    return max(numbers)


def create_ticket_folder(tasks_dir: Path, ticket_number: int) -> Path:
    folder = tasks_dir / str(ticket_number)
    folder.mkdir(parents=True, exist_ok=False)

    logger.info(
        'Создана папка заявки: %s',
        folder,
    )

    return folder


def copy_report_to_ticket_folder(
    report_file: Path,
    ticket_folder: Path,
) -> Path:
    destination = ticket_folder / report_file.name

    shutil.copy2(report_file, destination)

    logger.info(
        'Отчет скопирован в папку заявки: %s',
        destination,
    )

    return destination