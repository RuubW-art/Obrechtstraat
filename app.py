import streamlit as st
import json
import os
import requests
from datetime import datetime, time, timedelta
from icalendar import Calendar
import pytz

# =========================
# CONFIG
# =========================
NAMEN = ["Ruben", "Enzio", "Thijs"]
DATA_FILE = "status.json"
TIMEZONE = "Europe/Amsterdam"

# Plak hier je echte Google Calendar ICS-link
ICS_URL = "https://calendar.google.com/calendar/ical/addc6d0a5f6338ade0d17c610fdd190cd108e14da794e125b7b1ee45547bc3aa%40group.calendar.google.com/private-4642a193a3e058105329ccc65e76f7a8/basic.ics"

tz = pytz.timezone(TIMEZONE)

# =========================
# PAGE
# =========================
st.set_page_config(
    page_title="Werkplaats",
    page_icon="🔧",
    layout="centered"
)

# =========================
# CSS
# =========================
st.markdown("""
<style>
.main-title {
    text-align: center;
    font-size: 2.2rem;
    font-weight: 800;
    margin-bottom: 0.5rem;
}

.big-status {
    padding: 18px;
    border-radius: 18px;
    text-align: center;
    font-size: 1.8rem;
    font-weight: 800;
    color: white;
    margin-bottom: 10px;
}

.status-green { background: #1f9d55; }
.status-red { background: #d64545; }
.status-orange { background: #d98e04; }

.person-card {
    padding: 14px;
    border-radius: 18px;
    text-align: center;
    color: white;
    font-weight: 800;
    margin-bottom: 8px;
    min-height: 100px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.person-green { background: #1f9d55; }
.person-red { background: #d64545; }

.person-name {
    font-size: 1.5rem;
    margin-bottom: 6px;
}

.person-sub {
    font-size: 0.95rem;
    opacity: 0.95;
}

.choice-box {
    border: 2px solid #dddddd;
    border-radius: 16px;
    padding: 16px;
    margin-top: 10px;
    margin-bottom: 12px;
}

.small-note {
    color: #666666;
    font-size: 0.95rem;
}
</style>
""", unsafe_allow_html=True)

# =========================
# STORAGE
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "last_reset": None}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "last_reset": None}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_local():
    return datetime.now(tz)


def ensure_local(dt):
    if dt.tzinfo is None:
        return tz.localize(dt)
    return dt.astimezone(tz)


def reset_if_needed(data):
    now = now_local()
    reset_clock = time(6, 0)

    last_reset_str = data.get("last_reset")

    if not last_reset_str:
        data["last_reset"] = now.isoformat()
        save_data(data)
        return data

    try:
        last_reset = datetime.fromisoformat(last_reset_str)
        last_reset = ensure_local(last_reset)
    except Exception:
        last_reset = now

    if now.date() != last_reset.date() and now.time() >= reset_clock:
        data["users"] = {}
        data["last_reset"] = now.isoformat()
        save_data(data)

    return data


def cleanup_expired_checkins(data):
    changed = False
    now = now_local()

    for naam in list(data.get("users", {}).keys()):
        info = data["users"][naam]
        until_iso = info.get("until")

        if until_iso:
            try:
                until_dt = ensure_local(datetime.fromisoformat(until_iso))
                if now >= until_dt:
                    del data["users"][naam]
                    changed = True
            except Exception:
                pass

    if changed:
        save_data(data)

    return data

# =========================
# TIME HELPERS
# =========================
def round_up_to_next_quarter(dt):
    minute = dt.minute
    if minute == 0 and dt.second == 0 and dt.microsecond == 0:
        rounded_minute = 0
    elif minute <= 15:
        rounded_minute = 15
    elif minute <= 30:
        rounded_minute = 30
    elif minute <= 45:
        rounded_minute = 45
    else:
        rounded_minute = 0
        dt = dt + timedelta(hours=1)

    return dt.replace(minute=rounded_minute, second=0, microsecond=0)


def make_until_from_choice(choice, custom_time=None):
    now = now_local()

    if choice == "Onbekend":
        return None, "Onbekend"

    if choice == "+1 uur":
        until_dt = round_up_to_next_quarter(now + timedelta(hours=1))
        return until_dt.isoformat(), until_dt.strftime("%H:%M")

    if choice == "+2 uur":
        until_dt = round_up_to_next_quarter(now + timedelta(hours=2))
        return until_dt.isoformat(), until_dt.strftime("%H:%M")

    if choice == "Zelf tijd kiezen" and custom_time is not None:
        until_dt = now.replace(
            hour=custom_time.hour,
            minute=custom_time.minute,
            second=0,
            microsecond=0
        )
        if until_dt <= now:
            until_dt = until_dt + timedelta(days=1)

        return until_dt.isoformat(), until_dt.strftime("%H:%M")

    return None, "Onbekend"

# =========================
# GOOGLE CALENDAR
# =========================
def get_calendar_events_today():
    if not ICS_URL or ICS_URL == "PLAK_HIER_JE_ICS_LINK":
        return []

    try:
        response = requests.get(ICS_URL, timeout=10)
        response.raise_for_status()

        cal = Calendar.from_ical(response.text)
        now = now_local()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        events = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            dtstart = component.get("dtstart")
            dtend = component.get("dtend")
            summary = component.get("summary")

            if not dtstart or not dtend:
                continue

            start = dtstart.dt
            end = dtend.dt

            if not isinstance(start, datetime) or not isinstance(end, datetime):
                continue

            start = ensure_local(start)
            end = ensure_local(end)

            if end >= start_of_today and start <= end_of_today:
                events.append({
                    "summary": str(summary) if summary else "Agenda-item",
                    "start": start,
                    "end": end
                })

        events.sort(key=lambda x: x["start"])
        return events

    except Exception as e:
        st.warning(f"Agenda kon niet worden gelezen: {e}")
        return []


def get_active_calendar_events(events):
    now = now_local()
    return [e for e in events if e["start"] <= now <= e["end"]]


def get_future_calendar_events_today(events):
    now = now_local()
    return [e for e in events if e["start"] > now]


def get_next_calendar_event(events):
    future_events = get_future_calendar_events_today(events)
    if future_events:
        return future_events[0]
    return None

# =========================
# CHECK-IN LOGIC
# =========================
def check_in(data, naam, status, until_iso, until_label):
    data["users"][naam] = {
        "status": status,
        "time": now_local().strftime("%H:%M"),
        "until": until_iso,
        "until_label": until_label
    }
    save_data(data)


def check_out(data, naam):
    if naam in data["users"]:
        del data["users"][naam]
        save_data(data)

# =========================
# STATUS LOGIC
# =========================
def get_next_free_time(manual_users, calendar_events):
    now = now_local()
    active_events = get_active_calendar_events(calendar_events)

    if active_events:
        return max(e["end"] for e in active_events)

    alone_users = []
    for naam, info in manual_users.items():
        if info.get("status") == "Alleen":
            alone_users.append((naam, info))

    if alone_users:
        end_times = []
        unknown_present = False

        for _, info in alone_users:
            until_iso = info.get("until")
            if until_iso:
                try:
                    until_dt = ensure_local(datetime.fromisoformat(until_iso))
                    if until_dt > now:
                        end_times.append(until_dt)
                except Exception:
                    unknown_present = True
            else:
                unknown_present = True

        if unknown_present and not end_times:
            return None

        if end_times:
            return max(end_times)

        return None

    next_event = get_next_calendar_event(calendar_events)
    if next_event:
        return next_event["start"]

    return None


def compute_global_status(manual_users, calendar_events):
    active_events = get_active_calendar_events(calendar_events)

    if active_events:
        first_event = active_events[0]
        return {
            "label": "🚫 BEZET",
            "type": "red",
            "message": f"De werkplaats is gereserveerd via de agenda: {first_event['summary']} ({first_event['start'].strftime('%H:%M')}–{first_event['end'].strftime('%H:%M')})"
        }

    for naam, info in manual_users.items():
        if info.get("status") == "Alleen":
            until_label = info.get("until_label", "Onbekend")
            if until_label != "Onbekend":
                return {
                    "label": "🚫 BEZET",
                    "type": "red",
                    "message": f"{naam} is aanwezig en wil alleen werken tot ongeveer {until_label}."
                }
            return {
                "label": "🚫 BEZET",
                "type": "red",
                "message": f"{naam} is aanwezig en wil alleen werken. Eindtijd onbekend."
            }

    if manual_users:
        return {
            "label": "⚠️ IN GEBRUIK",
            "type": "orange",
            "message": "Er is iemand aanwezig, maar anderen zijn welkom."
        }

    next_event = get_next_calendar_event(calendar_events)
    if next_event:
        return {
            "label": "✅ VRIJ",
            "type": "green",
            "message": f"Nu vrij. Volgende reservering start om {next_event['start'].strftime('%H:%M')}."
        }

    return {
        "label": "✅ VRIJ",
        "type": "green",
        "message": "Niemand is ingecheckt."
    }

# =========================
# SESSION STATE
# =========================
if "pending_checkin_name" not in st.session_state:
    st.session_state.pending_checkin_name = None

if "chosen_status" not in st.session_state:
    st.session_state.chosen_status = None

if "chosen_duration" not in st.session_state:
    st.session_state.chosen_duration = "Onbekend"

# =========================
# LOAD
# =========================
data = load_data()
data = reset_if_needed(data)
data = cleanup_expired_checkins(data)

if "users" not in data:
    data["users"] = {}

calendar_events = get_calendar_events_today()
global_status = compute_global_status(data["users"], calendar_events)
next_free_time = get_next_free_time(data["users"], calendar_events)
active_events = get_active_calendar_events(calendar_events)
future_events = get_future_calendar_events_today(calendar_events)
next_event = get_next_calendar_event(calendar_events)

# =========================
# HEADER
# =========================
st.markdown('<div class="main-title">🔧 Werkplaats</div>', unsafe_allow_html=True)

status_class = {
    "green": "status-green",
    "red": "status-red",
    "orange": "status-orange"
}[global_status["type"]]

st.markdown(
    f'<div class="big-status {status_class}">{global_status["label"]}</div>',
    unsafe_allow_html=True
)
st.write(global_status["message"])

if next_free_time:
    st.info(f"Vrij vanaf ongeveer {next_free_time.strftime('%H:%M')}")
else:
    if global_status["type"] == "red":
        st.info("Vrij vanaf: onbekend")
    else:
        st.info("Geen eindtijd nodig: de werkplaats is nu vrij of deelbaar.")

if next_event:
    st.caption(
        f"Volgende reservering vandaag: {next_event['start'].strftime('%H:%M')}–{next_event['end'].strftime('%H:%M')}"
    )

if active_events:
    with st.expander("Agenda-item dat nu loopt"):
        for event in active_events:
            st.write(
                f"**{event['summary']}** — {event['start'].strftime('%H:%M')}–{event['end'].strftime('%H:%M')}"
            )

# =========================
# PERSON CARDS
# =========================
st.markdown("### Klik op je naam")

cols = st.columns(len(NAMEN))

for i, naam in enumerate(NAMEN):
    aanwezig = naam in data["users"]

    if aanwezig:
        info = data["users"][naam]
        until_text = info.get("until_label", "Onbekend")
        card_html = f"""
        <div class="person-card person-green">
            <div class="person-name">{naam}</div>
            <div class="person-sub">AANWEZIG · {info['status']} · sinds {info['time']}</div>
            <div class="person-sub">Tot: {until_text}</div>
        </div>
        """
    else:
        card_html = f"""
        <div class="person-card person-red">
            <div class="person-name">{naam}</div>
            <div class="person-sub">NIET AANWEZIG</div>
        </div>
        """

    with cols[i]:
        st.markdown(card_html, unsafe_allow_html=True)

        if st.button(naam, key=f"btn_{naam}", use_container_width=True):
            if aanwezig:
                check_out(data, naam)
                if st.session_state.pending_checkin_name == naam:
                    st.session_state.pending_checkin_name = None
                st.session_state.chosen_status = None
                st.session_state.chosen_duration = "Onbekend"
                st.rerun()
            else:
                st.session_state.pending_checkin_name = naam
                st.session_state.chosen_status = None
                st.session_state.chosen_duration = "Onbekend"
                st.rerun()

# =========================
# CHECK-IN FLOW
# =========================
pending_name = st.session_state.pending_checkin_name

if pending_name and pending_name not in data["users"]:
    st.markdown("### Inchecken")
    st.markdown(
        f"""
        <div class="choice-box">
            <strong>{pending_name}</strong> wil inchecken.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write("**1. Kies status**")
    c1, c2 = st.columns(2)

    with c1:
        if st.button("🚫 Alleen", use_container_width=True, key="choice_alleen"):
            st.session_state.chosen_status = "Alleen"
            st.rerun()

    with c2:
        if st.button("🙌 Anderen welkom", use_container_width=True, key="choice_welkom"):
            st.session_state.chosen_status = "Anderen welkom"
            st.rerun()

    if st.session_state.chosen_status:
        st.write(f"Gekozen status: **{st.session_state.chosen_status}**")

        st.write("**2. Kies duur**")
        duration_choice = st.radio(
            "Hoe lang ongeveer?",
            ["Onbekend", "+1 uur", "+2 uur", "Zelf tijd kiezen"],
            index=["Onbekend", "+1 uur", "+2 uur", "Zelf tijd kiezen"].index(st.session_state.chosen_duration),
            key="duration_radio"
        )
        st.session_state.chosen_duration = duration_choice

        custom_time = None

        if duration_choice == "Zelf tijd kiezen":
            default_dt = round_up_to_next_quarter(now_local() + timedelta(hours=1))
            custom_time = st.time_input(
                "Tot hoe laat?",
                value=default_dt.time(),
                step=900,
                key="until_time_picker"
            )
            st.caption(f"Inchecken tot ongeveer {custom_time.strftime('%H:%M')}")
        elif duration_choice == "+1 uur":
            preview_dt = round_up_to_next_quarter(now_local() + timedelta(hours=1))
            st.caption(f"Inchecken tot ongeveer {preview_dt.strftime('%H:%M')}")
        elif duration_choice == "+2 uur":
            preview_dt = round_up_to_next_quarter(now_local() + timedelta(hours=2))
            st.caption(f"Inchecken tot ongeveer {preview_dt.strftime('%H:%M')}")
        else:
            st.caption("Geen eindtijd ingesteld.")

        c3, c4 = st.columns(2)

        with c3:
            if st.button("✅ Bevestigen", use_container_width=True, key="confirm_checkin"):
                until_iso, until_label = make_until_from_choice(duration_choice, custom_time)
                check_in(
                    data=data,
                    naam=pending_name,
                    status=st.session_state.chosen_status,
                    until_iso=until_iso,
                    until_label=until_label
                )
                st.session_state.pending_checkin_name = None
                st.session_state.chosen_status = None
                st.session_state.chosen_duration = "Onbekend"
                st.rerun()

        with c4:
            if st.button("Annuleren", use_container_width=True, key="cancel_checkin"):
                st.session_state.pending_checkin_name = None
                st.session_state.chosen_status = None
                st.session_state.chosen_duration = "Onbekend"
                st.rerun()

# =========================
# TODAY SCHEDULE
# =========================
st.markdown("### Vandaag nog gepland")

if future_events:
    for event in future_events:
        st.write(
            f"**{event['start'].strftime('%H:%M')}–{event['end'].strftime('%H:%M')}** — {event['summary']}"
        )
else:
    st.info("Geen reserveringen meer vandaag.")

# =========================
# OVERVIEW
# =========================
st.markdown("### Overzicht")

if not data["users"]:
    st.info("Niemand is handmatig ingecheckt.")
else:
    for naam, info in data["users"].items():
        st.write(
            f"**{naam}** — {info['status']} "
            f"(sinds {info['time']}, tot {info.get('until_label', 'Onbekend')})"
        )

st.markdown(
    '<div class="small-note">Check-ins worden elke dag na 06:00 automatisch gereset.</div>',
    unsafe_allow_html=True
)