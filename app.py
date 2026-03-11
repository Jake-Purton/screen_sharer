# app.py
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay

pcs = set()
routes = web.RouteTableDef()
relay = MediaRelay()

# Latest tracks published by the broadcaster.
latest_video_track = None
latest_audio_track = None

@routes.get("/")
async def index(request):
    return web.FileResponse("index.html")

@routes.get("/viewer")
async def viewer(request):
    return web.FileResponse("viewer.html")

@routes.post("/offer/broadcast")
async def offer_broadcast(request):
    global latest_video_track, latest_audio_track

    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
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

    pc = RTCPeerConnection()
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
web.run_app(app, port=8080)