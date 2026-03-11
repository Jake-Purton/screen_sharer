import os
from collections import deque

from aiohttp import WSMsgType, web

routes = web.RouteTableDef()

# One active broadcaster and many viewers.
broadcaster_ws = None
viewer_sockets = set()

# Keep a small rolling buffer so late-joining viewers can start quickly.
recent_chunks = deque(maxlen=12)

@routes.get("/")
async def index(request):
    return web.FileResponse("index.html")

@routes.get("/viewer")
async def viewer(request):
    return web.FileResponse("viewer.html")


@routes.get("/healthz")
async def healthz(request):
    return web.json_response({"ok": True, "viewers": len(viewer_sockets)})


@routes.get("/ws/broadcast")
async def ws_broadcast(request):
    global broadcaster_ws

    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    if broadcaster_ws is not None and not broadcaster_ws.closed:
        await broadcaster_ws.close(code=4000, message=b"Replaced by new broadcaster")

    broadcaster_ws = ws
    recent_chunks.clear()

    await ws.send_json({"type": "ready", "viewers": len(viewer_sockets)})

    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                chunk = msg.data
                recent_chunks.append(chunk)

                stale = []
                for viewer_ws in viewer_sockets:
                    if viewer_ws.closed:
                        stale.append(viewer_ws)
                        continue
                    try:
                        await viewer_ws.send_bytes(chunk)
                    except ConnectionResetError:
                        stale.append(viewer_ws)

                for closed_ws in stale:
                    viewer_sockets.discard(closed_ws)

            elif msg.type == WSMsgType.TEXT:
                if msg.data == "ping":
                    await ws.send_str("pong")
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        if broadcaster_ws is ws:
            broadcaster_ws = None

    return ws


@routes.get("/ws/viewer")
async def ws_viewer(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    viewer_sockets.add(ws)

    # New viewers get a short warm-up buffer for quicker start.
    for chunk in recent_chunks:
        try:
            await ws.send_bytes(chunk)
        except ConnectionResetError:
            break

    await ws.send_json(
        {
            "type": "status",
            "broadcasterConnected": broadcaster_ws is not None and not broadcaster_ws.closed,
        }
    )

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT and msg.data == "ping":
                await ws.send_str("pong")
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        viewer_sockets.discard(ws)

    return ws

app = web.Application()
app.add_routes(routes)

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "30003"))
web.run_app(app, host=host, port=port)