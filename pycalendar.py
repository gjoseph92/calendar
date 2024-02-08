"""Generate a printable calendar in PDF format, suitable for embedding
into another document.

Tested with Python 3.11.

Dependencies:
- Python
- Reportlab

Resources Used:
- https://stackoverflow.com/a/37443801/435253
  (Originally present at http://billmill.org/calendar )
- https://www.reportlab.com/docs/reportlab-userguide.pdf

Originally created by Bill Mill on 11/16/05, this script is in the public
domain. There are no express warranties, so if you mess stuff up with this
script, it's not my fault.

Refactored and improved 2017-11-23 by Stephan Sokolow (http://ssokolow.com/).

TODO:
- Implement diagonal/overlapped cells for months which touch six weeks to avoid
  wasting space on six rows.
"""
import calendar
import collections
import datetime
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

from reportlab.lib import pagesizes, units
from reportlab.pdfgen.canvas import Canvas
import typer

# Supporting languages like French should be as simple as editing this
ORDINALS = {
    1: "st",
    2: "nd",
    3: "rd",
    21: "st",
    22: "nd",
    23: "rd",
    31: "st",
    None: "th",
}


# Enum support in Typer seems pretty broken. Only appears to work with enums with string
# values, so we have to have this Enum just to define the names, then the `PAPER_SIZES`
# dict to define the values.
class PaperSize(Enum):
    letter = "letter"
    legal = "legal"
    label_4x6 = "label_4x6"
    label_4x8 = "label_4x8"


PAPER_SIZES = {
    PaperSize.letter: pagesizes.letter,
    PaperSize.legal: pagesizes.legal,
    PaperSize.label_4x6: (4 * units.inch, 6 * units.inch),
    PaperSize.label_4x8: (4 * units.inch, 8 * units.inch),
}

# Something to help make code more readable
Font = collections.namedtuple("Font", ["name", "size"])
Geom = collections.namedtuple("Geom", ["x", "y", "width", "height"])
Size = collections.namedtuple("Size", ["width", "height"])


@contextmanager
def save_state(canvas):
    """Simple context manager to tidy up saving and restoring canvas state"""
    canvas.saveState()
    yield
    canvas.restoreState()


def add_calendar_page(
    canvas, rect, datetime_obj, cell_cb, ordinals, first_weekday=calendar.SUNDAY
):
    """Create a one-month pdf calendar, and return the canvas

    @param rect: A C{Geom} or 4-item iterable of floats defining the shape of
        the calendar in points with any margins already applied.
    @param datetime_obj: A Python C{datetime} object specifying the month
        the calendar should represent.
    @param cell_cb: A callback taking (canvas, day, rect, font, ordinals) as arguments
        which will be called to render each cell.
        (C{day} will be 0 for empty cells.)
    @param ordinals: Whether to add ordinals after the date number

    @type canvas: C{reportlab.pdfgen.canvas.Canvas}
    @type rect: C{Geom}
    @type cell_cb: C{function(Canvas, int, Geom, Font, bool)}
    @type ordinals: C{bool}
    """
    calendar.setfirstweekday(first_weekday)
    cal = calendar.monthcalendar(datetime_obj.year, datetime_obj.month)
    rect = Geom(*rect)

    # set up constants
    scale_factor = min(rect.width, rect.height)
    line_width = scale_factor * 0.0025
    font = Font("Helvetica", scale_factor * 0.028)
    rows = len(cal)

    # Leave room for the stroke width around the outermost cells
    rect = Geom(
        rect.x + line_width,
        rect.y + line_width,
        rect.width - (line_width * 2),
        rect.height - (line_width * 2),
    )
    cellsize = Size(rect.width / 7, rect.height / rows)

    # now fill in the day numbers and any data
    for row, week in enumerate(cal):
        for col, day in enumerate(week):
            # Give each call to cell_cb a known canvas state
            with save_state(canvas):
                # Set reasonable default drawing parameters
                canvas.setFont(*font)
                canvas.setLineWidth(line_width)

                cell_cb(
                    canvas,
                    day,
                    Geom(
                        x=rect.x + (cellsize.width * col),
                        y=rect.y + ((rows - row) * cellsize.height),
                        width=cellsize.width,
                        height=cellsize.height,
                    ),
                    font,
                    ordinals,
                )

    # Draw the month, year label
    with save_state(canvas):
        # Set reasonable default drawing parameters
        canvas.setFont(*font)
        canvas.setLineWidth(line_width)

        # Draw in upper-left unless the month starts on the first day of the week, then lower-right
        row, col = (0, 0) if cal[0][0] == 0 else (rows - 1, 6)

        draw_month_label(
            canvas,
            datetime_obj.year,
            datetime_obj.month,
            Geom(
                x=rect.x + (cellsize.width * col),
                y=rect.y + ((rows - row) * cellsize.height),
                width=cellsize.width,
                height=cellsize.height,
            ),
            font,
        )

    # finish this page
    canvas.showPage()
    return canvas


def draw_cell(canvas, day, rect, font, ordinals):
    """Draw a calendar cell with the given characteristics

    @param day: The date in the range 0 to 31.
    @param rect: A Geom(x, y, width, height) tuple defining the shape of the
        cell in points.
    @param ordinals: Whether to add ordinals after the date number

    @type rect: C{Geom}
    @type font: C{Font}
    @type ordinals: C{bool}
    """
    # Skip drawing cells that don't correspond to a date in this month
    if not day:
        return

    margin = Size(font.size * 0.5, font.size * 1.3)

    # Draw the cell border
    canvas.rect(rect.x, rect.y - rect.height, rect.width, rect.height)

    day = str(day)

    # Draw the number
    text_x = rect.x + margin.width
    text_y = rect.y - margin.height
    canvas.drawString(text_x, text_y, day)

    if ordinals:
        # Draw the lifted ordinal number suffix
        ordinal_str = ORDINALS.get(int(day), ORDINALS[None])
        number_width = canvas.stringWidth(day, font.name, font.size)
        canvas.drawString(
            text_x + number_width, text_y + (margin.height * 0.1), ordinal_str
        )


def draw_month_label(canvas, year, month, rect, font):
    margin = Size(font.size * 0.5, font.size * 1.3)

    text_x = rect.x + margin.width
    text_y = rect.y - margin.height
    text = f"{calendar.month_abbr[month]} {year}"

    canvas.drawString(text_x, text_y, text)


def generate_pdf(
    datetime_obj, outfile, size, ordinals=False, first_weekday=calendar.SUNDAY
):
    """Helper to apply add_calendar_page to save a ready-to-print file to disk.

    @param datetime_obj: A Python C{datetime} object specifying the month
        the calendar should represent.
    @param outfile: The path to which to write the PDF file.
    @param size: A (width, height) tuple (specified in points) representing
        the target page size.
    @param ordinals: Whether to add ordinals after the date number
    """
    size = Size(*size)
    canvas = Canvas(outfile, size)

    # margins
    wmar, hmar = size.width / 50, size.height / 50
    size = Size(size.width - (2 * wmar), size.height - (2 * hmar))

    add_calendar_page(
        canvas,
        Geom(wmar, hmar, size.width, size.height),
        datetime_obj,
        draw_cell,
        ordinals,
        first_weekday,
    ).save()


if __name__ == "__main__":
    now = datetime.datetime.now()

    def cli(
        year: int = now.year,
        month: int = now.month,
        file: Path = Path("calendar.pdf"),
        size: PaperSize = PaperSize.letter.value,  # type:ignore some bug in Typer
        landscape: bool = True,
        ordinals: bool = False,
    ):
        size_tuple = PAPER_SIZES[size]
        if landscape:
            size_tuple = pagesizes.landscape(size_tuple)
        generate_pdf(
            datetime.datetime(year, month, 1), str(file), size_tuple, ordinals=ordinals
        )

    typer.run(cli)
