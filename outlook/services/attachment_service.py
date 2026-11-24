"""Attachment listing, safe download, and (large-file) upload."""
import base64
import mimetypes
import re
from pathlib import Path

SIMPLE_LIMIT = 3 * 1024 * 1024
CHUNK = 320 * 1024 * 10          # 3.2 MB, a multiple of 320 KiB as Graph requires
MAX_UPLOAD = 150 * 1024 * 1024


def _safe_name(name):
    name = Path(str(name or "attachment")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "attachment"


class AttachmentService:

    def __init__(self, graph_client):
        self.graph = graph_client

    def list_attachments(self, message_id):
        return self.graph.get_all(
            f"me/messages/{message_id}/attachments",
            params={"$select": "id,name,contentType,size,isInline"}, max_items=100)

    def download_attachment(self, message_id, attachment_id,
                            save_directory="downloads/outlook"):
        meta = self.graph.get(f"me/messages/{message_id}/attachments/{attachment_id}",
                              params={"$select": "id,name,size,contentType"})
        if str(meta.get("@odata.type", "")).endswith("itemAttachment"):
            raise ValueError("Embedded Outlook items cannot be downloaded as files.")

        content = self.graph.get_bytes(
            f"me/messages/{message_id}/attachments/{attachment_id}/$value")

        directory = Path(save_directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / _safe_name(meta.get("name"))
        counter = 1
        while path.exists():                       # never overwrite an existing file
            path = directory / f"{path.stem}_{counter}{path.suffix}"
            counter += 1
        path.write_bytes(content)
        return str(path)

    def upload_attachment(self, message_id, file_path):
        """Attach a local file to a DRAFT message (uses an upload session if large)."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        size = path.stat().st_size
        if size > MAX_UPLOAD:
            raise ValueError("Attachments larger than 150 MB are not supported.")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        if size <= SIMPLE_LIMIT:
            return self.graph.post(f"me/messages/{message_id}/attachments", {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": path.name, "contentType": content_type,
                "contentBytes": base64.b64encode(path.read_bytes()).decode("ascii")})

        session = self.graph.post(
            f"me/messages/{message_id}/attachments/createUploadSession",
            {"AttachmentItem": {"attachmentType": "file", "name": path.name,
                                "size": size, "contentType": content_type}})
        url, result = session["uploadUrl"], {}
        with path.open("rb") as handle:
            start = 0
            while start < size:
                chunk = handle.read(CHUNK)
                end = start + len(chunk) - 1
                result = self.graph.put_chunk(url, chunk, start, end, size)
                start = end + 1
        return result
