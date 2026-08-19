from datetime import date, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlparse

from vp_data import ResourceNotFound, Unauthorized, fetch_week_plans
from web_utils import (
    COMMON_CSS,
    format_week_value,
    join_cookie_list,
    make_cookie,
    parse_cookie_header,
    parse_week,
    query_value,
    query_values,
    redirect,
    send_html,
    split_cookie_list,
    start_server,
)

DAY_NAMES = {
    0: "Mo",
    1: "Di",
    2: "Mi",
    3: "Do",
    4: "Fr",
}


def format_time(value) -> str:
    """Formatiert eine Uhrzeit für die Ausgabe."""

    if value is None:
        return ""

    return value.strftime("%H:%M")


def format_tuple(values: tuple[str, ...]) -> str:
    """Formatiert mehrere Werte als kurzen Text."""

    if not values:
        return "-"

    return ", ".join(str(value) for value in values)


def get_lesson_status_text(lesson) -> str:
    """Gibt den Status einer Stunde zurück."""

    if lesson.ausfall:
        return "Ausfall"

    if lesson.änderung:
        return "Vertretung"

    return "Regulär"


def get_lesson_subject_label(lesson) -> str:
    """Erzeugt eine Fach-Lehrer-Bezeichnung für den Filter."""

    subject = lesson.fach or "Unbekannt"
    teacher = format_tuple(lesson.lehrer)

    return f"{subject} ({teacher})"


def get_selected_subject_cookie_name(class_name: str) -> str:
    """Erzeugt einen Cookie-Namen für die Fachauswahl einer Klasse."""

    safe_class_name = "".join(
        char
        for char in class_name
        if char.isalnum() or char in ("-", "_")
    )

    return f"selected_subjects_{safe_class_name}"


def get_available_classes(week_plans: dict[date, object | None]) -> list[str]:
    """Sammelt alle Klassen, die in mindestens einem Wochenplan vorkommen."""

    classes = set()

    for plan in week_plans.values():
        if plan is None:
            continue

        classes.update(plan.klassen.keys())

    return sorted(classes)


def get_class_subject_options(week_plans: dict[date, object | None], class_name: str) -> list[str]:
    """Sammelt nur Fächer, die in der ausgewählten Klasse in dieser Woche vorkommen."""

    subjects = set()

    for plan in week_plans.values():
        if plan is None or class_name not in plan.klassen:
            continue

        class_item = plan.klassen[class_name]

        for lesson_items in class_item.stunden.values():
            for lesson in lesson_items:
                subjects.add(get_lesson_subject_label(lesson))

    return sorted(subjects)


def lesson_matches_subject_filter(lesson, selected_subjects: list[str]) -> bool:
    """Prüft, ob eine Stunde zum Fachfilter passt."""

    if not selected_subjects:
        return True

    return get_lesson_subject_label(lesson) in selected_subjects


def collect_week_lessons(
    week_plans: dict[date, object | None],
    class_name: str,
    selected_subjects: list[str],
) -> dict[int, dict[date, list]]:
    """Sammelt Stunden einer Klasse für Montag bis Freitag."""

    week_lessons: dict[int, dict[date, list]] = {}

    for plan_date, plan in week_plans.items():
        if plan is None or class_name not in plan.klassen:
            continue

        class_item = plan.klassen[class_name]

        for period, lesson_items in class_item.stunden.items():
            for lesson in lesson_items:
                if not lesson_matches_subject_filter(lesson, selected_subjects):
                    continue

                week_lessons.setdefault(int(period), {}).setdefault(plan_date, []).append(lesson)

    return week_lessons


def render_class_selection(week_plans: dict[date, object | None], selected_date: date) -> str:
    """Rendert die Klassenauswahl."""

    class_links = []

    for class_name in get_available_classes(week_plans):
        query = urlencode({
            "woche": format_week_value(selected_date),
            "klasse": class_name,
        })

        class_links.append(
            f'<a class="choice-card" href="/?{query}">{escape(class_name)}</a>'
        )

    if not class_links:
        return '<p class="empty">Es wurden keine Klassen gefunden.</p>'

    return f"""
        <section class="message">
            <h2>Klasse auswählen</h2>
            <p>Wähle deine Klasse aus. Die Auswahl wird im Browser gespeichert.</p>
        </section>

        <section class="choice-grid">
            {"".join(class_links)}
        </section>
    """


def render_subject_filter(
    week_plans: dict[date, object | None],
    selected_date: date,
    selected_class: str,
    selected_subjects: list[str],
) -> str:
    """Rendert die Fachauswahl für die ausgewählte Klasse."""

    subject_options = []

    for subject_label in get_class_subject_options(week_plans, selected_class):
        checked = "checked" if subject_label in selected_subjects else ""

        subject_options.append(f"""
            <label class="subject-option">
                <input type="checkbox" name="fach" value="{escape(subject_label)}" {checked}>
                <span>{escape(subject_label)}</span>
            </label>
        """)

    if not subject_options:
        return ""

    return f"""
        <section class="filter-card">
            <details>
                <summary>Fächer filtern</summary>

                <form method="get" action="/" class="subject-form">
                    <input type="hidden" name="woche" value="{selected_date.isoformat()}">
                    <input type="hidden" name="klasse" value="{escape(selected_class)}">

                    <div class="subject-grid">
                        {"".join(subject_options)}
                    </div>

                    <div class="filter-actions">
                        <button type="submit">Filter speichern</button>
                        <a class="button button-secondary" href="/?woche={selected_date.isoformat()}&klasse={escape(selected_class)}&fach_clear=1">
                            Filter löschen
                        </a>
                    </div>
                </form>
            </details>
        </section>
    """


def render_lesson_details(lesson) -> str:
    """Erzeugt den Detailbereich einer Stunde."""

    rows = [
        ("Zeit", f"{format_time(lesson.beginn)} - {format_time(lesson.ende)}"),
        ("Fach", lesson.fach or "-"),
        ("Lehrer", format_tuple(lesson.lehrer)),
        ("Raum", format_tuple(lesson.räume)),
        ("Status", get_lesson_status_text(lesson)),
        ("Info", lesson.info or "-"),
    ]

    return "".join(
        f"""
            <div class="popup-row">
                <span>{escape(label)}</span>
                <strong>{escape(value)}</strong>
            </div>
        """
        for label, value in rows
    )


def render_lesson_cell(lessons: list) -> str:
    """Rendert eine Tabellenzelle mit einer oder mehreren Stunden."""

    if not lessons:
        return '<div class="week-empty">-</div>'

    cards = []

    for lesson in lessons:
        changed_class = "week-lesson--changed" if lesson.änderung or lesson.ausfall else ""

        cards.append(f"""
            <details class="week-lesson {changed_class}">
                <summary>
                    <strong>{escape(lesson.fach or "-")}</strong>
                    <span>{escape(format_tuple(lesson.lehrer))}</span>
                    <span>{escape(format_tuple(lesson.räume))}</span>
                </summary>

                <div class="popup-content">
                    {render_lesson_details(lesson)}
                </div>
            </details>
        """)

    return "".join(cards)


def render_week_table(
    week_plans: dict[date, object | None],
    selected_class: str,
    selected_subjects: list[str],
) -> str:
    """Rendert den Wochenplan von Montag bis Freitag."""

    week_lessons = collect_week_lessons(week_plans, selected_class, selected_subjects)

    if not week_lessons:
        return '<p class="empty">Für diese Woche wurden keine Stunden gefunden.</p>'

    dates = list(week_plans.keys())
    max_period = max(8, max(week_lessons.keys(), default=8))

    header_cells = []

    for plan_date in dates:
        day_name = DAY_NAMES.get(plan_date.weekday(), plan_date.strftime("%a"))
        header_cells.append(f"""
            <th>
                <span>{escape(day_name)}</span>
                <small>{plan_date.strftime("%d.%m.")}</small>
            </th>
        """)

    rows = []

    for period in range(1, max_period + 1):
        day_cells = []

        for plan_date in dates:
            lessons = week_lessons.get(period, {}).get(plan_date, [])
            day_cells.append(f"<td>{render_lesson_cell(lessons)}</td>")

        rows.append(f"""
            <tr>
                <th class="period-head">{period}</th>
                {"".join(day_cells)}
            </tr>
        """)

    return f"""
        <section class="week-table-wrap">
            <table class="week-table">
                <thead>
                    <tr>
                        <th class="period-head">Std.</th>
                        {"".join(header_cells)}
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </section>
    """


def get_week_title(week_plans: dict[date, object | None]) -> str:
    """Erzeugt einen Titel für die angezeigte Woche."""

    dates = list(week_plans.keys())

    if not dates:
        return "Woche"

    return f"{dates[0].strftime('%d.%m.')} - {dates[-1].strftime('%d.%m.%Y')}"


def get_latest_timestamp_text(week_plans: dict[date, object | None]) -> str:
    """Gibt den neuesten bekannten Planstand der Woche zurück."""

    timestamps = [
        plan.zeitstempel
        for plan in week_plans.values()
        if plan is not None and plan.zeitstempel is not None
    ]

    if not timestamps:
        return "unbekannt"

    return max(timestamps).strftime("%d.%m.%Y %H:%M")


def render_week_navigation(selected_date: date, selected_class: str | None) -> str:
    """Rendert die Navigation für die vorherige und nächste Schulwoche."""

    previous_week = selected_date - timedelta(days=7)
    next_week = selected_date + timedelta(days=7)
    current_week = date.today() - timedelta(days=date.today().weekday())
    class_query = f"&{urlencode({'klasse': selected_class})}" if selected_class else ""

    return f"""
        <div class="week-navigation" aria-label="Wochennavigation">
            <a class="week-nav-button" href="/?woche={format_week_value(previous_week)}{class_query}" aria-label="Vorherige Woche">
                <span aria-hidden="true">‹</span>
                <small>Zurück</small>
            </a>

            <a class="week-nav-button week-nav-button--current" href="/?woche={format_week_value(current_week)}{class_query}">
                <span aria-hidden="true">⌂</span>
                <small>Aktuelle Woche</small>
            </a>

            <a class="week-nav-button" href="/?woche={format_week_value(next_week)}{class_query}" aria-label="Nächste Woche">
                <span aria-hidden="true">›</span>
                <small>Weiter</small>
            </a>
        </div>
    """


def render_plan_page(
    selected_date: date,
    selected_class: str | None = None,
    selected_subjects: list[str] | None = None,
    error_message: str | None = None,
) -> str:
    """Erzeugt die komplette Wochenplan-Seite."""

    selected_subjects = selected_subjects or []
    content = ""
    week_title = selected_date.strftime("%d.%m.%Y")
    plan_timestamp_text = "unbekannt"

    if error_message:
        content = f"""
            <section class="message message--error">
                <h2>Keine Daten verfügbar</h2>
                <p>{escape(error_message)}</p>
            </section>
        """
    else:
        week_plans = fetch_week_plans(selected_date)
        week_title = get_week_title(week_plans)
        plan_timestamp_text = get_latest_timestamp_text(week_plans)

        available_classes = get_available_classes(week_plans)

        if not selected_class or selected_class not in available_classes:
            content = render_class_selection(week_plans, selected_date)
        else:
            content = f"""
                <section class="message class-message">
                    <div>
                        <h2>Klasse {escape(selected_class)}</h2>
                        <p>Wochenplan von Montag bis Freitag. Tippe eine Stunde an, um Details zu sehen.</p>
                    </div>

                    <a class="button button-secondary" href="/?woche={selected_date.isoformat()}&klasse_clear=1">
                        Andere Klasse wählen
                    </a>
                </section>

                {render_subject_filter(week_plans, selected_date, selected_class, selected_subjects)}

                {render_week_table(week_plans, selected_class, selected_subjects)}
            """

    return f"""<!doctype html>
<html lang="de">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Vertretungsplan</title>
    <style>
        {COMMON_CSS}

        main {{
            width: min(1320px, calc(100% - 24px));
        }}

        .class-message {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            justify-content: space-between;
        }}

        .filter-card {{
            margin-bottom: 18px;
            padding: 18px 20px;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
        }}

        details summary {{
            cursor: pointer;
        }}

        .subject-form {{
            margin-top: 16px;
        }}

        .subject-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
            gap: 10px;
            margin-bottom: 16px;
        }}

        .subject-option {{
            display: flex;
            gap: 8px;
            align-items: center;
            min-height: 42px;
            padding: 9px 11px;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: var(--surface-muted);
            color: var(--text);
        }}

        .subject-option input {{
            width: auto;
            height: auto;
            flex: 0 0 auto;
        }}

        .subject-option span {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .filter-actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .button-secondary {{
            background: var(--surface-muted);
            color: var(--text);
            border: 1px solid var(--border);
        }}

        .button-secondary:hover {{
            background: #e8edf5;
        }}

        .week-navigation {{
            display: grid;
            grid-template-columns: minmax(190px, 1fr) minmax(240px, 1.25fr) minmax(190px, 1fr);
            gap: 14px;
            align-items: center;
            width: 100%;
        }}

        .week-nav-button {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            min-height: 64px;
            padding: 8px 14px;
            border: 1px solid #c7d2fe;
            border-radius: 16px;
            background: #eef2ff;
            color: var(--primary-dark);
            text-decoration: none;
            font-weight: 900;
        }}

        .week-nav-button--current {{
            background: var(--primary);
            border-color: var(--primary);
            color: white;
        }}

        .week-nav-button--current:hover {{
            background: var(--primary-dark);
            border-color: var(--primary-dark);
        }}

        .week-nav-button:hover {{
            background: #e0e7ff;
            border-color: var(--primary);
        }}

        .week-nav-button span {{
            font-size: 2rem;
            line-height: 1;
        }}

        .week-nav-button small {{
            font-size: 0.85rem;
        }}

        .week-table-wrap {{
            overflow-x: auto;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 18px;
            box-shadow: 0 8px 24px rgba(16, 24, 40, 0.06);
        }}

        .week-table {{
            width: 100%;
            min-width: 760px;
            border-collapse: collapse;
            table-layout: fixed;
        }}

        .week-table th,
        .week-table td {{
            border-bottom: 1px solid var(--border);
            border-right: 1px solid var(--border);
            padding: 6px;
            vertical-align: top;
        }}

        .week-table th:last-child,
        .week-table td:last-child {{
            border-right: 0;
        }}

        .week-table tr:last-child th,
        .week-table tr:last-child td {{
            border-bottom: 0;
        }}

        .week-table thead th {{
            position: sticky;
            top: 0;
            z-index: 2;
            background: var(--surface-muted);
            font-size: 0.9rem;
        }}

        .week-table thead span,
        .week-table thead small {{
            display: block;
        }}

        .week-table thead small {{
            color: var(--muted);
            font-weight: 700;
        }}

        .period-head {{
            width: 44px;
            background: var(--surface-muted);
            text-align: center;
            font-weight: 900;
        }}

        .week-empty {{
            min-height: 58px;
            display: grid;
            place-items: center;
            color: var(--muted);
            font-weight: 700;
        }}

        .week-lesson {{
            position: relative;
            margin-bottom: 6px;
        }}

        .week-lesson:last-child {{
            margin-bottom: 0;
        }}

        .week-lesson summary {{
            display: grid;
            gap: 2px;
            min-height: 58px;
            padding: 7px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: white;
            list-style: none;
        }}

        .week-lesson summary::-webkit-details-marker {{
            display: none;
        }}

        .week-lesson--changed summary {{
            background: #fee2e2;
            border-color: #fca5a5;
        }}

        .week-lesson strong,
        .week-lesson span {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .week-lesson strong {{
            font-size: 0.88rem;
        }}

        .week-lesson span {{
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 700;
        }}

        .popup-content {{
            position: absolute;
            z-index: 20;
            left: 0;
            top: calc(100% + 6px);
            width: min(310px, calc(100vw - 32px));
            padding: 14px;
            background: white;
            border: 1px solid var(--border);
            border-radius: 14px;
            box-shadow: 0 18px 48px rgba(16, 24, 40, 0.22);
        }}

        .popup-row {{
            display: grid;
            grid-template-columns: 78px 1fr;
            gap: 10px;
            padding: 7px 0;
            border-bottom: 1px solid var(--border);
        }}

        .popup-row:last-child {{
            border-bottom: 0;
        }}

        .popup-row span {{
            color: var(--muted);
            font-size: 0.82rem;
            font-weight: 800;
        }}

        .popup-row strong {{
            min-width: 0;
            overflow-wrap: anywhere;
        }}

        @media (max-width: 900px) {{
            main {{
                width: min(100% - 14px, 900px);
            }}

            .week-table {{
                min-width: 0;
            }}

            .week-table th,
            .week-table td {{
                padding: 4px;
            }}

            .period-head {{
                width: 32px;
                font-size: 0.78rem;
            }}

            .week-table thead th {{
                font-size: 0.74rem;
            }}

            .week-table thead small {{
                font-size: 0.66rem;
            }}

            .week-lesson summary {{
                min-height: 48px;
                padding: 5px;
                border-radius: 8px;
            }}

            .week-lesson strong {{
                font-size: 0.72rem;
            }}

            .week-lesson span {{
                font-size: 0.62rem;
            }}

            .week-empty {{
                min-height: 48px;
                font-size: 0.7rem;
            }}

            .subject-grid {{
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            }}
        }}

        @media (max-width: 620px) {{
            main {{
                width: calc(100% - 8px);
                padding: 10px 0;
            }}

            .brand h1 {{
                font-size: 1.55rem;
            }}

            .brand p,
            .meta {{
                font-size: 0.82rem;
            }}

            .panel,
            .message,
            .filter-card {{
                padding: 12px;
                border-radius: 14px;
            }}

            .class-message {{
                display: grid;
            }}

            .week-navigation {{
                grid-template-columns: 1fr 1.25fr 1fr;
                gap: 10px;
            }}

            .week-nav-button {{
                min-height: 48px;
                padding: 6px 8px;
                gap: 4px;
            }}

            .week-nav-button span {{
                font-size: 1.55rem;
            }}

            .week-nav-button small {{
                font-size: 0.72rem;
            }}

            .filter-actions {{
                display: grid;
            }}

            .subject-grid {{
                grid-template-columns: 1fr;
            }}

            .week-table-wrap {{
                border-radius: 12px;
            }}

            .week-table th,
            .week-table td {{
                padding: 3px;
            }}

            .period-head {{
                width: 26px;
                font-size: 0.68rem;
            }}

            .week-table thead th {{
                font-size: 0.66rem;
            }}

            .week-table thead small {{
                font-size: 0.58rem;
            }}

            .week-lesson summary {{
                min-height: 42px;
                padding: 4px;
            }}

            .week-lesson strong {{
                font-size: 0.64rem;
            }}

            .week-lesson span {{
                font-size: 0.56rem;
            }}

            .week-empty {{
                min-height: 42px;
                font-size: 0.62rem;
            }}

            .popup-content {{
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: min(340px, calc(100vw - 24px));
            }}
        }}
    </style>
</head>
<body>
    <main>
        <header class="topbar">
            <div class="brand">
                <h1>Vertretungsplan</h1>
                <p>Woche {escape(week_title)}</p>
            </div>

            <nav class="nav">
                <a class="active" href="/">Klassen</a>
                <a href="/lehrer">Lehrer</a>
                <a href="/raeume">Freie Räume</a>
            </nav>
        </header>

        <section class="panel">
            {render_week_navigation(selected_date, selected_class)}

            <div class="meta">
                Neuester Planstand: {escape(plan_timestamp_text)}
            </div>
        </section>

        {content}
    </main>
</body>
</html>"""


class PlanPageHandler(BaseHTTPRequestHandler):
    """HTTP-Handler für die Vertretungsplan-Seite."""

    def do_GET(self):
        """Verarbeitet GET-Anfragen."""

        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        browser_cookies = parse_cookie_header(self.headers.get("Cookie"))

        selected_date = parse_week(query_value(query, "woche"))
        selected_class = query_value(query, "klasse") or browser_cookies.get("selected_class")
        selected_subjects = []
        cookie_headers = []

        if query_value(query, "klasse_clear") == "1":
            selected_class = None
            cookie_headers.append(make_cookie("selected_class", "", max_age=0))

        subject_cookie_name = get_selected_subject_cookie_name(selected_class) if selected_class else None

        if selected_class and subject_cookie_name:
            selected_subjects = (
                query_values(query, "fach")
                or split_cookie_list(browser_cookies.get(subject_cookie_name))
            )

        if query_value(query, "fach_clear") == "1":
            selected_subjects = []

            if subject_cookie_name:
                cookie_headers.append(make_cookie(subject_cookie_name, "", max_age=0))

        if selected_class:
            cookie_headers.append(make_cookie("selected_class", selected_class))

        if selected_class and subject_cookie_name and "fach" in query:
            cookie_headers.append(make_cookie(subject_cookie_name, join_cookie_list(selected_subjects)))

        try:
            html = render_plan_page(selected_date, selected_class, selected_subjects)
        except ResourceNotFound:
            html = render_plan_page(
                selected_date,
                selected_class,
                selected_subjects,
                error_message="Für diese Woche wurden keine Vertretungsplandaten gefunden.",
            )
        except Unauthorized:
            html = render_plan_page(
                selected_date,
                selected_class,
                selected_subjects,
                error_message="Die Zugangsdaten sind ungültig oder haben keinen Zugriff auf diese Daten.",
            )
        except Exception as error:
            html = render_plan_page(
                selected_date,
                selected_class,
                selected_subjects,
                error_message=f"Beim Laden der Daten ist ein Fehler aufgetreten: {error}",
            )

        if query_value(query, "klasse_clear") == "1":
            redirect(self, f"/?woche={selected_date.isoformat()}", cookie_headers)
            return

        send_html(self, html, cookie_headers)

    def log_message(self, format, *args):
        """Unterdrückt HTTP-Logs."""

        return


def main():
    """Startet nur die Vertretungsplan-Seite."""

    start_server(PlanPageHandler, "Vertretungsplan-Seite")


if __name__ == "__main__":
    main()
