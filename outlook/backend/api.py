"""HTTP API for connecting and managing Outlook identities."""
import base64
import html
from urllib.parse import parse_qs

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from outlook.backend.auth_service import AuthenticationError, OutlookAuthService
from outlook.backend.config import BackendSettings
from outlook.backend.graph_proxy import validate_graph_request
from outlook.services.graph_client import GraphAPIError, GraphClient


class ConnectionStart(BaseModel):
    email: str


class ConnectionPoll(BaseModel):
    transaction_id: str
    transaction_secret: str


class GraphRequest(BaseModel):
    method: str
    endpoint: str
    params: dict | None = None
    body: object | None = None
    headers: dict | None = None
    content_type: str | None = "application/json"
    raw: bool = False


def create_app(settings=None, auth_service=None):
    settings = settings or BackendSettings.from_env()
    auth_service = auth_service or OutlookAuthService(settings)
    app = FastAPI(title="Ghost Outlook Authentication", docs_url=None, redoc_url=None)
    app.state.outlook_auth = auth_service

    def current_session(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required.")
        return authorization[7:].strip()

    @app.post("/auth/start")
    def start_connection(body: ConnectionStart):
        try:
            return auth_service.start_connection(body.email)
        except AuthenticationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/auth/callback", response_class=HTMLResponse)
    async def microsoft_callback(request: Request):
        raw_body = await request.body()
        try:
            response_data = {
                key: value[-1]
                for key, value in parse_qs(
                    raw_body.decode("utf-8"), keep_blank_values=True
                ).items()
            }
        except (UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid Microsoft response.") from exc
        state = response_data.get("state", "")
        try:
            transaction_id = auth_service.store.find_transaction_id(state)
            if not transaction_id:
                raise AuthenticationError(
                    "Microsoft sign-in expired or could not be validated. Start again."
                )
            auth_service.complete_connection(transaction_id, response_data)
        except AuthenticationError as exc:
            message = html.escape(str(exc))
            return HTMLResponse(
                f"<!doctype html><html><body><h1>Outlook connection failed</h1>"
                f"<p>{message}</p><p>Return to Ghost and try again.</p></body></html>",
                status_code=400,
            )
        return HTMLResponse(
            "<!doctype html><html><body><h1>Outlook connected</h1>"
            "<p>Return to Ghost to finish connecting your account.</p></body></html>"
        )

    @app.post("/auth/poll")
    def poll_connection(body: ConnectionPoll):
        result = auth_service.poll_connection(
            body.transaction_id, body.transaction_secret
        )
        if result["status"] == "invalid":
            raise HTTPException(status_code=404, detail="Connection request not found.")
        return result

    @app.get("/account/status")
    def account_status(authorization: str = Header(default="")):
        token = current_session(authorization)
        try:
            return auth_service.get_account_status(token)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.delete("/account")
    def disconnect_account(authorization: str = Header(default="")):
        token = current_session(authorization)
        try:
            return auth_service.disconnect(token)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.post("/graph/request")
    def graph_request(
        body: GraphRequest,
        authorization: str = Header(default=""),
    ):
        session_token = current_session(authorization)
        try:
            validate_graph_request(
                body.method,
                body.endpoint,
                body.body,
                body.headers,
                body.raw,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            graph = GraphClient(
                token_provider=lambda: auth_service.acquire_access_token(
                    session_token
                )
            )
            response = graph._send(
                body.method,
                graph._url(body.endpoint),
                params=body.params,
                json_data=body.body,
                extra_headers=body.headers,
                content_type=body.content_type,
                raw=body.raw,
            )
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except GraphAPIError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "graph_status": exc.status,
                    "code": exc.code,
                    "message": str(exc),
                },
            ) from exc

        if body.raw:
            return {"content_base64": base64.b64encode(response.content).decode("ascii")}
        return response

    return app


def main():
    import uvicorn

    settings = BackendSettings.from_env()
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=8765,
        access_log=False,
    )


if __name__ == "__main__":
    main()
