# Deploy screen_share to k3s

Low-latency browser screen streaming using **WebCodecs + WebSockets**.  
No WebRTC, no UDP; works through Cloudflare Tunnel.

## Architecture

```
Sender browser                     Server (Node.js)              Viewer browser
──────────────                     ────────────────              ──────────────
getDisplayMedia()                  WS /ws/broadcast              WS /ws/viewer
  → VideoTrackProcessor            relay binary chunks →         → MediaSource
  → VideoEncoder (VP9, realtime)   cache init segment            → SourceBuffer (VP9/WebM)
  → webm-muxer (chunked clusters)  for late joiners              → <video> element
  → WS /ws/broadcast
```

**Sender** encodes with WebCodecs (VP9, `latencyMode:'realtime'`) and wraps
frames in WebM clusters via `webm-muxer`.  One cluster is sent every ~167 ms
(keyframe every 5 frames at 30 fps).

**Server** relays binary clusters to all viewers.  The first cluster
(WebM init segment: EBML + Tracks) is cached so late-joining viewers can
start decoding immediately.

**Viewer** feeds clusters into a MSE `SourceBuffer` (`mode:'sequence'`) and
applies live-edge correction to stay within ~0.1 s of real-time.

Target end-to-end latency: **< 300 ms** over a local Cloudflare Tunnel.

Browser support: Chrome 94+, Firefox 130+.  Safari is not supported (VP9
encoding requires Chrome/Firefox).

---

## Run locally (Node.js)

```bash
npm install
node server.js
# Sender:  http://localhost:30003/
# Viewer:  http://localhost:30003/viewer
```

## Run with Docker

```bash
docker build -t screen-share:local .
docker run --rm -p 30003:30003 screen-share:local
```

## Published image

```text
ghcr.io/jake-purton/screen_sharer:latest
```

```bash
docker pull ghcr.io/jake-purton/screen_sharer:latest
docker run --rm -p 30003:30003 ghcr.io/jake-purton/screen_sharer:latest
```

## Deploy to k3s

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

Environment variables (configured in `k8s/deployment.yaml`):

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `30003` | Listen port |

## Push an updated image

```bash
docker build -t screen-share:local .
docker tag screen-share:local ghcr.io/jake-purton/screen_sharer:latest
docker push ghcr.io/jake-purton/screen_sharer:latest
kubectl rollout restart deployment/screen-share
```

kubectl apply -f k8s/service.yaml
```

## 5) Verify rollout

```bash
kubectl get pods -l app=screen-share
kubectl get svc screen-share
kubectl port-forward svc/screen-share 8080:80
```

Use:
- http://localhost:8080
- http://localhost:8080/viewer

## Notes on latency

- Latency is controlled mostly by MediaRecorder chunk size.
- Current implementation sends chunks every 250ms.
- Lower values reduce latency but increase CPU/network overhead.
