# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The limits this app's Streamlit server keeps, in the desktop app and in a
source run alike: desktop_launcher.py's server child and run_source.py's
call hold_the_server before Streamlit reads its configuration or builds its
server. Standard library only at import; Streamlit is loaded by the call.
"""
import os

# The route by which every client sends a file to the server. The app has no
# file uploader, so the route is refused outright.
UPLOAD_ROUTE = "/_stcore/upload_file"

# The page's fonts, the one thing this server answers by file name: these names
# alone, from the fonts folder beside the app. No folder is served as files, so
# no other name, method or spelling of a path reaches the disk.
FONT_ROUTE = "/zij-font/"
FONT_FILES = frozenset({
    "dejavu-sans-400.ttf", "eb-garamond-400-italic.ttf", "eb-garamond-400.ttf", "eb-garamond-600.ttf",
    "tae-symbols-400.ttf", "tae-symbols2-400.ttf",
    "zij-interface-400.ttf", "zij-interface-600.ttf", "zij-numeric-400.ttf",
})


def hold_the_server(app_path: str):
    """Five things Streamlit has no option for, set in the server's process
    before Streamlit reads its configuration or builds its server. The first
    three and the fifth each replace a name Streamlit looks up as it runs; the
    fourth listens for the parse. A Streamlit without a name these need stops the server here,
    before it listens.

    - Config files: only the config files of the .streamlit folder beside
      `app_path` (config.toml and secrets.toml) are read. A frozen build
      carries the checkout's config.toml, for its theme above all; the
      launcher's flags outrank what else it holds.
    - The public address: Streamlit asks an outside service for this
      computer's public address whenever a client's Origin is not a local
      one, waiting on the answer; here it is never asked, and such an
      Origin is refused as before, without the wait (one naming the public
      address among them). Origins on this computer, its network address
      among them, are let through as before (the launch's key still decides
      who is let in).
    - Every HTTP route answers only a request whose Host the session's
      connection would accept (server.allowedHosts, given as a flag), and no
      request reaches the upload route. Past that check, a GET of a name in
      FONT_FILES is answered with that font, sent with no header that lets
      another site read it, and anything else under FONT_ROUTE is not found.
    - The page's colours: the configuration, once parsed, takes the colours the
      reader saved (page_colours.py), so that a launch's first message carries
      them. One word from the reader's own preferences file (importing the data
      layer to read it makes the data folder and moves a former one across,
      waiting on that folder's lock if another program holds it, as the first
      session would a moment later), Light or Dark or else ignored; a file
      missing or unreadable starts the app as it would.
    - The page's own document: Streamlit's index.html, wherever its static
      handler serves it, is answered with the "Opening…" cover written into
      it in the colours in force (opening.py), so that the cover stands from
      the page's first paint. Its handler is the one wrapped: one that serves
      no index.html stops the server here."""
    from streamlit import config, net_util
    from streamlit.web.server.starlette import starlette_app, starlette_websocket

    import opening
    import page_colours

    app_folder = os.path.dirname(os.path.abspath(app_path))
    own_folder = os.path.join(app_folder, ".streamlit")
    for module, name in ((config, "get_config_files"), (config, "on_config_parsed"), (config, "set_option"),
                         (config, "get_options_for_section"), (net_util, "get_external_ip"),
                         (starlette_app, "create_streamlit_middleware"),
                         (starlette_app, "create_streamlit_static_assets_routes"),
                         (starlette_websocket, "_is_host_allowed")):
        if not callable(getattr(module, name, None)):
            raise RuntimeError(f"Streamlit has no {module.__name__}.{name}: the server is not started.")

    def get_config_files(file_name):
        return [os.path.join(own_folder, file_name)]

    def get_external_ip():
        return None

    host_allowed = starlette_websocket._is_host_allowed
    make_middleware = starlette_app.create_streamlit_middleware

    async def answer_font(scope, send):
        name = scope["path"][len(FONT_ROUTE):]
        body = None
        if scope["method"] == "GET" and name in FONT_FILES:
            try:
                with open(os.path.join(app_folder, "fonts", name), "rb") as f:
                    body = f.read()
            except OSError:
                pass
        status, kind = (200, b"font/ttf") if body is not None else (404, b"text/plain; charset=utf-8")
        body = b"" if body is None else body
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", kind), (b"content-length", str(len(body)).encode("ascii")),
                                (b"cache-control", b"no-cache"), (b"x-content-type-options", b"nosniff")]})
        await send({"type": "http.response.body", "body": body})

    class _OnlyThisServersRequests:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                hosts = [value.decode("latin-1") for key, value in scope["headers"] if key == b"host"]
                path = scope["path"]
                if (len(hosts) != 1 or not host_allowed(hosts[0])
                        or path == UPLOAD_ROUTE or path.startswith(UPLOAD_ROUTE + "/")):
                    await send({"type": "http.response.start", "status": 403,
                                "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                            (b"content-length", b"9")]})
                    await send({"type": "http.response.body", "body": b"Forbidden"})
                    return
                if path.startswith(FONT_ROUTE):
                    await answer_font(scope, send)
                    return
            await self.app(scope, receive, send)

    make_static_routes = starlette_app.create_streamlit_static_assets_routes

    def serving_the_cover(get_response, index_path):
        index_path = os.path.normcase(os.path.abspath(index_path))

        async def answer(path, scope):
            asked = scope.get("method") == "GET"
            if asked:
                # Asked whole each time, so the answer is always the one written.
                scope = {**scope, "headers": [(key, value) for key, value in scope.get("headers", [])
                                              if key not in (b"if-none-match", b"if-modified-since")]}
            response = await get_response(path, scope)
            served = getattr(response, "path", None)
            if not (asked and response.status_code == 200 and isinstance(served, str)
                    and os.path.normcase(os.path.abspath(served)) == index_path):
                return response
            from starlette.responses import HTMLResponse

            with open(index_path, encoding="utf-8") as f:
                document = opening.served(f.read(), page_colours.showing())
            return HTMLResponse(document, headers={"Cache-Control": "no-cache"})
        return answer

    def create_streamlit_static_assets_routes(*args, **kwargs):
        routes = make_static_routes(*args, **kwargs)
        for route in routes:
            files = getattr(route, "app", None)
            index_path = getattr(files, "_index_path", None)
            if not isinstance(index_path, str) or not callable(getattr(files, "get_response", None)):
                raise RuntimeError("Streamlit serves no index.html by its static handler: the server is not started.")
            files.get_response = serving_the_cover(files.get_response, index_path)
        return routes

    def create_streamlit_middleware():
        from starlette.middleware import Middleware

        return [Middleware(_OnlyThisServersRequests), *make_middleware()]

    config.on_config_parsed(page_colours.show_the_saved_choice, force_connect=True)
    config.get_config_files = get_config_files
    net_util.get_external_ip = get_external_ip
    starlette_app.create_streamlit_middleware = create_streamlit_middleware
    starlette_app.create_streamlit_static_assets_routes = create_streamlit_static_assets_routes
