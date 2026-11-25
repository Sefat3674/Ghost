class CalendarService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def get_events(self, start_datetime, end_datetime, limit=50):
        response = self.graph.get(
            "me/calendarView",
            params={
                "startDateTime": start_datetime,
                "endDateTime": end_datetime,
                "$top": limit,
                "$orderby": "start/dateTime",
                "$select": (
                    "id,subject,start,end,location,organizer,"
                    "isAllDay,isCancelled,webLink"
                )
            }
        )
        return response.get("value", [])

    def create_event(
        self,
        subject,
        start_datetime,
        end_datetime,
        timezone="UTC",
        body="",
        location=""
    ):
        if not subject:
            raise ValueError("Event subject is required.")

        data = {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body
            },
            "start": {
                "dateTime": start_datetime,
                "timeZone": timezone
            },
            "end": {
                "dateTime": end_datetime,
                "timeZone": timezone
            },
            "location": {
                "displayName": location
            }
        }

        return self.graph.post("me/events", data)

    def update_event(self, event_id, changes):
        return self.graph.patch(
            f"me/events/{event_id}",
            changes
        )

    def delete_event(self, event_id):
        return self.graph.delete(
            f"me/events/{event_id}"
        )
