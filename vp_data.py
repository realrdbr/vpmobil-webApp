from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import pickle, os, json

from vpmobil import ResourceNotFound, Unauthorized, VertretungsplanZugang

load_dotenv()

# Zugangsdaten für den Vertretungsplan.
SCHULNUMMER = os.getenv("SCHULNUMMER")
BENUTZERNAME = os.getenv("BENUTZERNAME")
PASSWORT = os.getenv("PASSWORT")


# Der Cache wird lokal im Projektordner gespeichert.
# Pro Datum wird genau eine Datei angelegt.
CACHE_DIR = Path(".vp_cache")
CACHE_DAYS = 7


# Feste Liste aller Räume, die grundsätzlich als verfügbar betrachtet werden können.
ALL_ROOMS = json.loads(os.getenv("ALL_ROOMS"))


ALPHABET = "abcdefghijklmnopqrstuvwxyz"


def log(message: str) -> None:
    """Gibt eine einheitlich formatierte Konsolenmeldung aus."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_cache_path(selected_date: date) -> Path:
    """Gibt den Dateipfad für den Cache eines bestimmten Datums zurück."""

    return CACHE_DIR / f"{selected_date.isoformat()}.pickle"


def cleanup_cache() -> None:
    """Löscht Cache-Dateien, deren Datum nicht mehr in den letzten sieben Tagen liegt."""

    if not CACHE_DIR.exists():
        return

    oldest_allowed_date = date.today() - timedelta(days=CACHE_DAYS - 1)

    for cache_file in CACHE_DIR.glob("*.pickle"):
        try:
            cached_date = date.fromisoformat(cache_file.stem)
        except ValueError:
            log(f"Ungültige Cache-Datei entfernt: {cache_file}")
            cache_file.unlink(missing_ok=True)
            continue

        if cached_date < oldest_allowed_date:
            log(f"Alter Cache entfernt: {cache_file}")
            cache_file.unlink(missing_ok=True)


def load_plan_from_cache(selected_date: date):
    """Lädt einen Vertretungsplan aus dem lokalen Cache."""

    cache_path = get_cache_path(selected_date)

    if not cache_path.exists():
        log(f"Kein Cache für {selected_date.isoformat()} gefunden.")
        return None

    try:
        with cache_path.open("rb") as file:
            plan = pickle.load(file)

        plan_timestamp = get_plan_timestamp(plan)
        timestamp_text = plan_timestamp.strftime("%d.%m.%Y %H:%M") if plan_timestamp else "unbekannt"

        log(f"Cache für {selected_date.isoformat()} geladen. Planstand: {timestamp_text}")
        return plan
    except (OSError, pickle.PickleError, EOFError):
        log(f"Cache für {selected_date.isoformat()} ist beschädigt und wird gelöscht.")
        cache_path.unlink(missing_ok=True)
        return None


def save_plan_to_cache(selected_date: date, plan) -> None:
    """Speichert einen Vertretungsplan im lokalen Cache."""

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cache_path = get_cache_path(selected_date)

    with cache_path.open("wb") as file:
        pickle.dump(plan, file)

    plan_timestamp = get_plan_timestamp(plan)
    timestamp_text = plan_timestamp.strftime("%d.%m.%Y %H:%M") if plan_timestamp else "unbekannt"

    log(f"Plan für {selected_date.isoformat()} im Cache gespeichert. Planstand: {timestamp_text}")


def get_plan_timestamp(plan) -> datetime | None:
    """Liest den Veröffentlichungszeitpunkt eines Plans aus."""

    return getattr(plan, "zeitstempel", None)


def is_remote_plan_newer(cached_plan, remote_plan) -> bool:
    """Prüft, ob der frisch geladene Plan neuer als der gecachte Plan ist."""

    cached_timestamp = get_plan_timestamp(cached_plan)
    remote_timestamp = get_plan_timestamp(remote_plan)

    # Wenn es bisher keinen Cache gibt, ist der geladene Plan automatisch relevant.
    if cached_plan is None:
        return True

    # Wenn der neue Plan keinen Zeitstempel hat, überschreiben wir den Cache nicht.
    # So bleibt ein bereits bekannter Plan erhalten.
    if remote_timestamp is None:
        return False

    # Wenn der alte Plan keinen Zeitstempel hat, ist ein neuer Plan mit Zeitstempel besser.
    if cached_timestamp is None:
        return True

    return remote_timestamp > cached_timestamp


def fetch_plan_from_vpmobil(selected_date: date):
    """Lädt den Vertretungsplan für das angegebene Datum direkt von VpMobil."""

    log(f"Prüfe VpMobil auf aktuellen Plan für {selected_date.isoformat()}.")

    access = VertretungsplanZugang(SCHULNUMMER, BENUTZERNAME, PASSWORT)
    plan = access.fetch(selected_date)

    plan_timestamp = get_plan_timestamp(plan)
    timestamp_text = plan_timestamp.strftime("%d.%m.%Y %H:%M") if plan_timestamp else "unbekannt"

    log(f"Plan von VpMobil geladen. Planstand: {timestamp_text}")

    return plan


def fetch_plan(selected_date: date):
    """Lädt den Plan, aktualisiert den Cache bei neueren Daten und nutzt sonst den alten Cache."""

    cleanup_cache()

    cached_plan = load_plan_from_cache(selected_date)

    try:
        remote_plan = fetch_plan_from_vpmobil(selected_date)
    except ResourceNotFound:
        if cached_plan is not None:
            log(f"VpMobil hat keinen Plan für {selected_date.isoformat()} geliefert. Nutze vorhandenen Cache.")
            return cached_plan

        log(f"VpMobil hat keinen Plan für {selected_date.isoformat()} geliefert und es gibt keinen Cache.")
        raise
    except Unauthorized:
        log("VpMobil-Zugriff verweigert. Zugangsdaten prüfen.")
        raise
    except Exception as error:
        if cached_plan is not None:
            log(f"VpMobil konnte nicht erreicht werden ({error}). Nutze vorhandenen Cache.")
            return cached_plan

        log(f"VpMobil konnte nicht erreicht werden ({error}) und es gibt keinen Cache.")
        raise

    if is_remote_plan_newer(cached_plan, remote_plan):
        log(f"Neuerer Plan für {selected_date.isoformat()} gefunden. Cache wird aktualisiert.")
        save_plan_to_cache(selected_date, remote_plan)
        return remote_plan

    log(f"Kein neuerer Plan für {selected_date.isoformat()} gefunden. Nutze vorhandenen Cache.")
    return cached_plan


def get_school_week_dates(selected_date: date) -> list[date]:
    """Gibt Montag bis Freitag der Woche zurück, in der das ausgewählte Datum liegt."""

    monday = selected_date - timedelta(days=selected_date.weekday())

    return [
        monday + timedelta(days=offset)
        for offset in range(5)
    ]


def fetch_week_plans(selected_date: date) -> dict[date, object | None]:
    """Lädt die verfügbaren Pläne von Montag bis Freitag einer Woche.

    Nicht verfügbare Tage werden als None gespeichert. So kann die Wochenansicht
    trotzdem angezeigt werden, auch wenn einzelne Tagespläne fehlen.
    """

    week_plans = {}

    for plan_date in get_school_week_dates(selected_date):
        try:
            week_plans[plan_date] = fetch_plan(plan_date)
        except ResourceNotFound:
            log(f"Kein Plan für {plan_date.isoformat()} verfügbar.")
            week_plans[plan_date] = None

    return week_plans


def collect_relevant_classes(plan) -> list:
    """Sammelt alle Klassen, die für die Raumbelegung ausgewertet werden sollen."""

    classes = []

    for grade in range(1, 13):
        main_class_found = False

        for letter in ALPHABET:
            class_name = f"{grade}{letter}"

            if class_name in plan.klassen:
                classes.append(plan.klassen[class_name])
                continue

            # Wenn es keine getrennten Klassen wie 11a oder 11b gibt,
            # wird einmalig die Hauptklasse wie "11" übernommen.
            if not main_class_found and str(grade) in plan.klassen:
                classes.append(plan.klassen[str(grade)])
                main_class_found = True

    return classes


def extract_room_number(room_value: object) -> int | None:
    """Extrahiert aus einem Raumwert die numerische Raumnummer."""

    digits = "".join(filter(str.isdigit, str(room_value)))

    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def find_occupied_rooms(classes: list, selected_hour: int) -> set[int]:
    """Ermittelt alle Räume, die in der angegebenen Stunde belegt sind."""

    occupied_rooms = set()

    for class_item in classes:
        for period, lessons in class_item.stunden.items():
            if int(period) != selected_hour:
                continue

            for lesson in lessons:
                for room in lesson.räume:
                    room_number = extract_room_number(room)

                    if room_number is not None:
                        occupied_rooms.add(room_number)

    return occupied_rooms


def find_free_rooms(selected_date: date, selected_hour: int) -> list[int]:
    """Gibt alle freien Räume für ein Datum und eine Unterrichtsstunde zurück."""

    plan = fetch_plan(selected_date)
    classes = collect_relevant_classes(plan)
    occupied_rooms = find_occupied_rooms(classes, selected_hour)

    return [room for room in ALL_ROOMS if room not in occupied_rooms]


__all__ = [
    "ResourceNotFound",
    "Unauthorized",
    "fetch_plan",
    "fetch_week_plans",
    "find_free_rooms",
]