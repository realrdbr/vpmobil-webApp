import os
from datetime import date, datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

load_dotenv()

DEFAULT_PORT = int(os.getenv("PORT", 8000))
DEFAULT_HOST = os.getenv("HOST", "127.0.0.1")


def parse_date(value: str | None) -> date:
    """Wandelt einen Formularwert in ein gültiges date-Objekt um."""

    if not value:
        return date.today()

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def parse_week(value: str | None) -> date:
    """Wandelt einen HTML-Wochenwert wie '2026-W34' in den Montag dieser Woche um."""

    if not value:
        today = date.today()
        return today - timedelta(days=today.weekday())

    try:
        year_text, week_text = value.split("-W", 1)
        return date.fromisocalendar(int(year_text), int(week_text), 1)
    except (ValueError, TypeError):
        today = date.today()
        return today - timedelta(days=today.weekday())


def format_week_value(selected_date: date) -> str:
    """Formatiert ein Datum als HTML-Wochenwert."""

    year, week, _ = selected_date.isocalendar()
    return f"{year}-W{week:02d}"


def parse_hour(value: str | None) -> int:
    """Wandelt einen Formularwert in eine gültige Unterrichtsstunde um."""

    try:
        hour = int(value or "1")
    except ValueError:
        return 1

    if hour < 1 or hour > 8:
        return 1

    return hour


def parse_cookie_header(cookie_header: str | None) -> dict[str, str]:
    """Liest Cookies aus dem Request-Header."""

    if not cookie_header:
        return {}

    parsed_cookies = cookies.SimpleCookie()
    parsed_cookies.load(cookie_header)

    return {
        key: morsel.value
        for key, morsel in parsed_cookies.items()
    }


def make_cookie(name: str, value: str, max_age: int = 60 * 60 * 24 * 180) -> str:
    """Erzeugt einen Cookie-Header."""

    cookie = cookies.SimpleCookie()
    cookie[name] = value
    cookie[name]["path"] = "/"
    cookie[name]["max-age"] = str(max_age)
    cookie[name]["samesite"] = "Lax"

    return cookie.output(header="").strip()


def send_html(handler: BaseHTTPRequestHandler, html: str, cookie_headers: list[str] | None = None) -> None:
    """Sendet eine HTML-Antwort an den Browser."""

    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")

    for cookie_header in cookie_headers or []:
        handler.send_header("Set-Cookie", cookie_header)

    handler.end_headers()
    handler.wfile.write(html.encode("utf-8"))


def redirect(handler: BaseHTTPRequestHandler, location: str, cookie_headers: list[str] | None = None) -> None:
    """Leitet den Browser weiter."""

    handler.send_response(303)
    handler.send_header("Location", location)

    for cookie_header in cookie_headers or []:
        handler.send_header("Set-Cookie", cookie_header)

    handler.end_headers()


def query_value(query: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    """Liest den ersten Wert eines Query-Parameters aus."""

    return query.get(name, [default])[0]


def query_values(query: dict[str, list[str]], name: str) -> list[str]:
    """Liest alle Werte eines Query-Parameters aus."""

    return query.get(name, [])


def split_cookie_list(value: str | None) -> list[str]:
    """Wandelt eine kommaseparierte Cookie-Liste in einzelne Werte um."""

    if not value:
        return []

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


def join_cookie_list(values: list[str]) -> str:
    """Wandelt eine Liste in einen kompakten Cookie-Wert um."""

    return ",".join(values)


def start_server(handler_class: type[BaseHTTPRequestHandler], title: str, port: int = DEFAULT_PORT) -> None:
    """Startet einen lokalen HTTP-Server."""

    server = ThreadingHTTPServer((DEFAULT_HOST, port), handler_class)

    print(f"{title} läuft unter http://{DEFAULT_HOST}:{port}")
    print("Zum Beenden Strg+C drücken.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer wird beendet.")
    finally:
        server.server_close()


COMMON_CSS = """
:root {
    --background: #f4f6f8;
    --surface: #ffffff;
    --surface-muted: #f8fafc;
    --primary: #2454d6;
    --primary-dark: #1d43aa;
    --text: #172033;
    --muted: #667085;
    --border: #d0d5dd;
    --changed-bg: #fff7ed;
    --cancelled-bg: #fef2f2;
    --error-bg: #fff1f1;
    --error-text: #a40000;
    --good-bg: #dcfce7;
    --good-border: #86efac;
    --good-text: #166534;
    --medium-bg: #fef3c7;
    --medium-border: #fcd34d;
    --medium-text: #92400e;
    --bad-bg: #fee2e2;
    --bad-border: #fca5a5;
    --bad-text: #991b1b;
    --unknown-bg: #f1f5f9;
    --unknown-border: #cbd5e1;
    --unknown-text: #334155;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;
    background: var(--background);
    color: var(--text);
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

main {
    width: min(1180px, calc(100% - 32px));
    margin: 0 auto;
    padding: 32px 0;
}

.topbar {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 22px;
}

.brand h1 {
    margin: 0 0 6px;
    font-size: clamp(2rem, 4vw, 3rem);
    line-height: 1.1;
}

.brand p {
    margin: 0;
    color: var(--muted);
}

.nav {
    display: flex;
    gap: 10px;
}

.nav a {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    padding: 0 16px;
    border-radius: 999px;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    text-decoration: none;
    font-weight: 800;
}

.nav a.active {
    background: var(--primary);
    border-color: var(--primary);
    color: white;
}

.panel {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    align-items: end;
    justify-content: space-between;
    padding: 20px;
    margin-bottom: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: 0 12px 32px rgba(16, 24, 40, 0.08);
}

.form-row {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: end;
}

label {
    display: grid;
    gap: 7px;
    color: var(--muted);
    font-weight: 700;
}

input,
select,
button {
    height: 42px;
    border-radius: 10px;
    font: inherit;
}

input,
select {
    border: 1px solid var(--border);
    padding: 0 12px;
    background: white;
    color: var(--text);
}

button,
.button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    border: 0;
    border-radius: 10px;
    padding: 0 18px;
    background: var(--primary);
    color: white;
    cursor: pointer;
    font: inherit;
    font-weight: 800;
    text-decoration: none;
}

button:hover,
.button:hover {
    background: var(--primary-dark);
}

.meta {
    color: var(--muted);
    font-size: 0.95rem;
}

.message {
    padding: 18px 20px;
    margin-bottom: 18px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
}

.message h2 {
    margin: 0 0 8px;
}

.message p {
    margin: 0;
    color: var(--muted);
}

.message--error {
    background: var(--error-bg);
    color: var(--error-text);
    border-color: #ffc9c9;
}

.empty {
    margin: 0;
    padding: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    color: var(--muted);
}

.choice-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
    gap: 12px;
}

.choice-card {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 58px;
    padding: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    color: var(--text);
    text-decoration: none;
    font-weight: 900;
    box-shadow: 0 6px 18px rgba(16, 24, 40, 0.06);
}

.choice-card:hover {
    border-color: var(--primary);
    color: var(--primary);
}

@media (max-width: 900px) {
    main {
        width: min(100% - 24px, 820px);
        padding: 24px 0;
    }

    .topbar {
        align-items: stretch;
    }

    .brand {
        width: 100%;
    }

    .nav {
        width: 100%;
    }

    .nav a {
        flex: 1;
    }

    .panel {
        align-items: stretch;
    }

    .form-row {
        width: 100%;
        display: grid;
        grid-template-columns: 1fr 1fr auto;
    }
}

@media (max-width: 620px) {
    main {
        width: min(100% - 18px, 520px);
        padding: 18px 0;
    }

    .brand h1 {
        font-size: 2rem;
    }

    .form-row {
        grid-template-columns: 1fr;
    }

    label,
    input,
    select,
    button,
    .button {
        width: 100%;
    }

    .panel {
        padding: 16px;
    }

    .choice-grid {
        grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
        gap: 10px;
    }
}
"""