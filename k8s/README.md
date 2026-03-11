# Deploy screen_share to k3s

This app now streams screen video/audio using plain WebSockets.

Broadcaster flow:
- Browser captures screen.
- Browser encodes chunks with MediaRecorder.
- Chunks are sent to `/ws/broadcast`.

Viewer flow:
- Viewer connects to `/ws/viewer`.
- Server fans out chunks to all connected viewers.

Published image:

```text
ghcr.io/jake-purton/screen_sharer:latest
```

If the package is private in GitHub Container Registry, either make it public in package settings or create an `imagePullSecret` in the cluster.

## 1) Pull and test the published image

```bash
docker pull ghcr.io/jake-purton/screen_sharer:latest
docker run --rm -p 30003:30003 ghcr.io/jake-purton/screen_sharer:latest
```

Open:
- http://localhost:30003
- http://localhost:30003/viewer

## 2) Build and test locally

```bash
docker build -t screen-share:local .
docker run --rm -p 30003:30003 screen-share:local
```

## 3) Tag and push image manually

```bash
docker tag screen-share:local ghcr.io/jake-purton/screen_sharer:latest
docker push ghcr.io/jake-purton/screen_sharer:latest
```

## 4) Apply manifests to k3s

```bash
kubectl apply -f k8s/deployment.yaml
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
