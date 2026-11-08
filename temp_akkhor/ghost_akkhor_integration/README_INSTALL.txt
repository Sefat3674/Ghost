GHOST + AKKHOR INTEGRATION PATCH
================================

WHAT IS INCLUDED
- ui.py: uploaded GHOST UI with an AKKHOR SCHOOL button and panel launcher.
- main.py: uploaded GHOST main module with Akkhor service wiring and one read-only Gemini tool.
- actions/akkhor/: JWT auth manager, API client, shared service, Tkinter panel.
- config/akkhor_config.json: API base URL and configurable GET endpoints.
- tests/test_akkhor_integration.py: local import/configuration smoke test.

INSTALL ON WINDOWS POWERSHELL
1. Stop GHOST.
2. Go to your GHOST project root, e.g.:
   cd E:\kaizumi\kaizumi
3. Back up the current files:
   Copy-Item .\ui.py .\ui.py.before_akkhor.bak
   Copy-Item .\main.py .\main.py.before_akkhor.bak
4. Extract this ZIP to a temporary folder. It contains a folder named
   ghost_akkhor_integration. Copy the CONTENTS of that folder into your
   GHOST project root, preserving relative folders, and allow ui.py/main.py
   to be overwritten.
5. Ensure config/akkhor_config.json has the correct Akkhor API URL.
6. Run:
   python -m py_compile .\ui.py .\main.py .\actions\akkhor\auth_manager.py .\actions\akkhor\akkhor_client.py .\actions\akkhor\service.py .\actions\akkhor\akkhor_panel.py
   python .\tests\test_akkhor_integration.py
7. Start GHOST as usual. Open AKKHOR SCHOOL from the left Command Deck.
8. Sign in using your normal Akkhor email/password. Do not paste passwords or
   JWTs into chat or source files.

WHAT WORKS IN THIS FIRST INTEGRATION
- Login using POST /api/Auth/login.
- JWT kept in memory only; no token/password persistence.
- Logout clears the in-memory token.
- Read-only GET requests for configured assignments, submissions, and users
  endpoints. Results are displayed as JSON in the panel.
- Gemini tool: akkhor_school with actions status, assignments, submissions,
  students. The tool requires a prior login in the panel.

IMPORTANT LIMITATIONS
- The exact list endpoint query parameters and response schemas have not yet
  been verified against your running Swagger. Default routes are configurable
  and the panel displays the API's actual response/error for diagnosis.
- No create, update, delete, grading, publishing, or payment actions are exposed.
- The role field returned by your login was null. GHOST does not infer roles;
  Akkhor's server-side authorization remains authoritative.
- Local HTTPS must use a trusted ASP.NET development certificate. On the
  backend machine, `dotnet dev-certs https --trust` may be needed.
- The smoke test checks imports/configuration only. It does not prove live API
  access from this computer; perform login with your running Akkhor backend.

ROLLBACK
Restore ui.py.before_akkhor.bak and main.py.before_akkhor.bak, then remove
only the newly added actions/akkhor directory and config/akkhor_config.json
if you did not have them before this patch.
