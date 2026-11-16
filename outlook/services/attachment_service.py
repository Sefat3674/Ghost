import base64
import mimetypes
from pathlib import Path

import requests

from outlook.config import (
    GRAPH_BASE_URL,
    REQUEST_TIMEOUT
)


class AttachmentService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def list_attachments(self, message_id):
        response = self.graph.get(
            f"me/messages/{message_id}/attachments"
        )
        return response.get("value", [])

    def download_attachment(
        self,
        message_id,
        attachment_id,
        save_directory="downloads/outlook"
    ):
        url = (
            f"{GRAPH_BASE_URL}/me/messages/"
            f"{message_id}/attachments/{attachment_id}/$value"
        )

        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {self.graph.access_token}"
            },
            timeout=REQUEST_TIMEOUT
        )

        if not response.ok:
            raise RuntimeError(
                f"Attachment download failed: HTTP {response.status_code}"
            )

        directory = Path(save_directory)
        directory.mkdir(parents=True, exist_ok=True)

        filename = response.headers.get(
            "Content-Disposition", ""
        )

        filename = filename.split("filename=")[-1].strip('"') if "filename=" in filename else "attachment"

        path = directory / Path(filename).name
        path.write_bytes(response.content)

        return str(path)

    def upload_attachment(self, message_id, file_path):
        path = Path(file_path)

        if not path.is_file():
            raise FileNotFoundError(str(path))

        if path.stat().st_size > 3 * 1024 * 1024:
            raise ValueError(
                "This simple upload supports files up to 3 MB. "
                "Use an upload session for larger files."
            )

        content_type = (
            mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        )

        data = {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": path.name,
            "contentType": content_type,
            "contentBytes": base64.b64encode(
                path.read_bytes()
            ).decode("ascii")
        }

        return self.graph.post(
            f"me/messages/{message_id}/attachments",
            data
        )
