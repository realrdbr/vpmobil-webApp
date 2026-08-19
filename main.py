from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from plan_page import (
    get_selected_subject_cookie_name,
    render_plan_page,
)
from rooms_page import render_rooms_page
from teacher_page import render_teacher_page
from vp_data import ResourceNotFound, Unauthorized, find_free_rooms
from web_utils import (
    format_week_value,
    join_cookie_list,
    make_cookie,
    parse_cookie_header,
    parse_hour,
    parse_week,
    query_value,
    query_values,
    redirect,
    send_html,
    split_cookie_list,
)
import os
from dotenv import load_dotenv

load_dotenv()


class AppRequestHandler(BaseHTTPRequestHandler):
    """Startet alle Unterseiten in einer gemeinsamen Webanwendung."""

    def do_GET(self):
        """Leitet Anfragen an die passende Seite weiter."""

        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)

        if parsed_url.path == "/raeume":
            self.handle_rooms_page(query)
            return

        if parsed_url.path == "/lehrer":
            self.handle_teacher_page(query)
            return

        self.handle_plan_page(query)

    def handle_plan_page(self, query: dict[str, list[str]]) -> None:
        """Rendert die Klassenseite."""

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

        if query_value(query, "klasse_clear") == "1":
            redirect(self, f"/?woche={format_week_value(selected_date)}", cookie_headers)
            return

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

        send_html(self, html, cookie_headers)

    def handle_teacher_page(self, query: dict[str, list[str]]) -> None:
        """Rendert die Lehrerplan-Seite."""

        browser_cookies = parse_cookie_header(self.headers.get("Cookie"))

        selected_date = parse_week(query_value(query, "woche"))
        selected_teacher = query_value(query, "lehrer") or browser_cookies.get("selected_teacher")
        cookie_headers = []

        if query_value(query, "lehrer_clear") == "1":
            selected_teacher = None
            cookie_headers.append(make_cookie("selected_teacher", "", max_age=0))

        if selected_teacher:
            cookie_headers.append(make_cookie("selected_teacher", selected_teacher))

        if query_value(query, "lehrer_clear") == "1":
            redirect(self, f"/lehrer?woche={format_week_value(selected_date)}", cookie_headers)
            return

        try:
            html = render_teacher_page(selected_date, selected_teacher)
        except ResourceNotFound:
            html = render_teacher_page(
                selected_date,
                selected_teacher,
                error_message="Für diese Woche wurden keine Lehrerdaten gefunden.",
            )
        except Unauthorized:
            html = render_teacher_page(
                selected_date,
                selected_teacher,
                error_message="Die Zugangsdaten sind ungültig oder haben keinen Zugriff auf diese Daten.",
            )
        except Exception as error:
            html = render_teacher_page(
                selected_date,
                selected_teacher,
                error_message=f"Beim Laden der Daten ist ein Fehler aufgetreten: {error}",
            )

        send_html(self, html, cookie_headers)

    def handle_rooms_page(self, query: dict[str, list[str]]) -> None:
        """Rendert die freie-Räume-Seite."""

        from web_utils import parse_date

        selected_date = parse_date(query_value(query, "datum"))
        selected_hour = parse_hour(query_value(query, "stunde"))

        free_rooms = None
        error_message = None

        try:
            free_rooms = find_free_rooms(selected_date, selected_hour)
        except ResourceNotFound:
            error_message = "Für dieses Datum wurden keine Vertretungsplandaten gefunden."
        except Unauthorized:
            error_message = "Die Zugangsdaten sind ungültig oder haben keinen Zugriff auf diese Daten."
        except Exception as error:
            error_message = f"Beim Laden der Daten ist ein Fehler aufgetreten: {error}"

        html = render_rooms_page(
            selected_date=selected_date,
            selected_hour=selected_hour,
            free_rooms=free_rooms,
            error_message=error_message,
        )

        send_html(self, html)

    def log_message(self, format, *args):
        """Unterdrückt HTTP-Logs."""

        return


def main():
    """Startet die gesamte lokale Webanwendung."""

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    server = ThreadingHTTPServer((host, port), AppRequestHandler)

    print(f"Webanwendung läuft unter http://{host}:{port}")
    print("Klassenseite: /")
    print("Lehrerseite: /lehrer")
    print("Freie Räume: /raeume")
    print("Zum Beenden Strg+C drücken.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer wird beendet.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()