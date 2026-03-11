# Deploy screen_share to k3s

The published container image for this repo is:

```text
ghcr.io/jake-purton/screen_sharer:latest
```

If the package is private in GitHub Container Registry, either make it public in the package settings or create an `imagePullSecret` in the cluster.

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

Open:
- http://localhost:30003
- http://localhost:30003/viewer

## 3) Tag and push image manually

The GitHub Actions workflow now publishes automatically to GHCR on pushes to `main`, so you usually do not need to do this by hand. If you want to push manually, use:

```bash
docker tag screen-share:local ghcr.io/jake-purton/screen_sharer:latest
docker push ghcr.io/jake-purton/screen_sharer:latest
```

## 4) Update deployment image

`k8s/deployment.yaml` should use:

```yaml
image: ghcr.io/jake-purton/screen_sharer:latest
```

## 5) Apply manifests to k3s

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## 6) Verify rollout

```bash
kubectl get pods -l app=screen-share
kubectl get svc screen-share
kubectl get ingress screen-share
```

## 7) Cloudflare Tunnel note

For this app, Cloudflare Tunnel can handle HTTP signaling (`/offer/*`), but WebRTC media may still require TURN for reliable public internet access.
