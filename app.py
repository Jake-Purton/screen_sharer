import os
import json

from aiohttp import web
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCIceServer,
)
from aiortc.contrib.media import MediaRelay

pcs = set()
routes = web.RouteTableDef()
relay = MediaRelay()

# Latest tracks published by the broadcaster.
latest_video_track = None
latest_audio_track = None


def load_ice_servers():
    raw = os.getenv("ICE_SERVERS_JSON", "")
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    normalized = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        urls = item.get("urls")
        if not isinstance(urls, (str, list)):
            continue

        normalized.append(
            {
                "urls": urls,
                "username": item.get("username"),
                "credential": item.get("credential"),
            }
        )

    return normalized


ICE_SERVERS = load_ice_servers()


def build_rtc_config():
    if not ICE_SERVERS:
        return RTCConfiguration(iceServers=[])

    servers = []
    for ice in ICE_SERVERS:
        servers.append(
            RTCIceServer(
                urls=ice["urls"],
                username=ice.get("username"),
                credential=ice.get("credential"),
            )
        )
    return RTCConfiguration(iceServers=servers)

@routes.get("/")
async def index(request):
    return web.FileResponse("index.html")

@routes.get("/viewer")
async def viewer(request):
    return web.FileResponse("viewer.html")


@routes.get("/config")
async def config(request):
    return web.json_response({"iceServers": ICE_SERVERS})

@routes.post("/offer/broadcast")
async def offer_broadcast(request):
    global latest_video_track, latest_audio_track

    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection(configuration=build_rtc_config())
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_state_change():
        if pc.connectionState in {"failed", "closed"}:
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        global latest_video_track, latest_audio_track

        if track.kind == "video":
            latest_video_track = track
        elif track.kind == "audio":
            latest_audio_track = track

        @track.on("ended")
        async def on_ended():
            if track.kind == "video" and latest_video_track is track:
                latest_video_track = None
            if track.kind == "audio" and latest_audio_track is track:
                latest_audio_track = None

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )

@routes.post("/offer/viewer")
async def offer_viewer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection(configuration=build_rtc_config())
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_state_change():
        if pc.connectionState in {"failed", "closed"}:
            await pc.close()
            pcs.discard(pc)

    # Subscribe each viewer to the latest published tracks.
    if latest_video_track is not None:
        pc.addTrack(relay.subscribe(latest_video_track))
    if latest_audio_track is not None:
        pc.addTrack(relay.subscribe(latest_audio_track))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response(
        {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
    )

app = web.Application()
app.add_routes(routes)

host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("PORT", "30003"))
web.run_app(app, host=host, port=port)