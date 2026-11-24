"""Calendar: view, create, update, delete, respond, and find free time."""
from datetime import datetime, timedelta, timezone

_SELECT = ("id,subject,start,end,location,organizer,attendees,isAllDay,isCancelled,"
           "webLink,onlineMeeting,responseStatus,bodyPreview,showAs")


def _attendees(value):
    if not value:
        return []
    if isinstance(value, str):
        value = [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]
    return [{"emailAddress": {"address": a}, "type": "required"} for a in value]


class CalendarService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def get_events(self, start_datetime, end_datetime, limit=50, tz=None):
        headers = {"Prefer": f'outlook.timezone="{tz}"'} if tz else None
        return self.graph.get_all(
            "me/calendarView",
            params={"startDateTime": start_datetime, "endDateTime": end_datetime,
                    "$top": min(limit, 50), "$orderby": "start/dateTime",
                    "$select": _SELECT},
            extra_headers=headers, max_items=limit)

    def get_event(self, event_id):
        return self.graph.get(f"me/events/{event_id}", params={"$select": _SELECT + ",body"})

    def create_event(self, subject, start_datetime, end_datetime, timezone="UTC",
                     body="", location="", attendees=None, all_day=False,
                     online_meeting=False, reminder_minutes=None):
        if not subject:
            raise ValueError("Event subject is required.")
        data = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body or ""},
            "start": {"dateTime": start_datetime, "timeZone": timezone},
            "end": {"dateTime": end_datetime, "timeZone": timezone},
            "isAllDay": bool(all_day),
        }
        if location:
            data["location"] = {"displayName": location}
        if attendees:
            data["attendees"] = _attendees(attendees)
        if online_meeting:
            data["isOnlineMeeting"] = True
            data["onlineMeetingProvider"] = "teamsForBusiness"
        if reminder_minutes is not None:
            data["isReminderOn"] = True
            data["reminderMinutesBeforeStart"] = int(reminder_minutes)
        return self.graph.post("me/events", data)

    def update_event(self, event_id, changes):
        return self.graph.patch(f"me/events/{event_id}", changes)

    def delete_event(self, event_id):
        return self.graph.delete(f"me/events/{event_id}")

    def cancel_event(self, event_id, comment=""):
        return self.graph.post(f"me/events/{event_id}/cancel", {"comment": comment})

    def respond(self, event_id, response, comment="", send_response=True):
        endpoint = {"accept": "accept", "tentative": "tentativelyAccept",
                    "decline": "decline"}.get(str(response).lower())
        if not endpoint:
            raise ValueError("response must be accept, tentative or decline.")
        return self.graph.post(f"me/events/{event_id}/{endpoint}",
                               {"comment": comment, "sendResponse": send_response})

    def find_free_slots(self, days=3, duration_minutes=30, work_start=9, work_end=17,
                        tz="UTC", limit=10):
        """Local free/busy scan inside working hours (works on all account types)."""
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)
        busy = []
        for ev in self.get_events(now.isoformat(), end.isoformat(), limit=200, tz="UTC"):
            if ev.get("isCancelled") or ev.get("showAs") == "free":
                continue
            s = datetime.fromisoformat(ev["start"]["dateTime"][:19]).replace(tzinfo=timezone.utc)
            e = datetime.fromisoformat(ev["end"]["dateTime"][:19]).replace(tzinfo=timezone.utc)
            busy.append((s, e))
        busy.sort()

        slots, step = [], timedelta(minutes=duration_minutes)
        for offset in range(days + 1):
            day = (now + timedelta(days=offset)).replace(minute=0, second=0, microsecond=0)
            cursor = max(day.replace(hour=work_start), now)
            day_end = day.replace(hour=work_end)
            while cursor + step <= day_end and len(slots) < limit:
                clash = next((b for b in busy if b[0] < cursor + step and b[1] > cursor), None)
                if clash:
                    cursor = max(clash[1], cursor + timedelta(minutes=15))
                    continue
                slots.append((cursor, cursor + step))
                cursor += step
        return slots
