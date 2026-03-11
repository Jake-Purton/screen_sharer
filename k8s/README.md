# Deploy screen_share to k3s

## 1) Build and test locally

```bash
docker build -t screen-share:local .
docker run --rm -p 30003:30003 screen-share:local
```

Open:
- http://localhost:30003
- http://localhost:30003/viewer

## 2) Tag and push image

Replace `ghcr.io/your-user` with your registry path:

```bash
docker tag screen-share:local ghcr.io/your-user/screen-share:latest
docker push ghcr.io/your-user/screen-share:latest
```

## 3) Update deployment image

Edit `k8s/deployment.yaml` and set:

```yaml
image: ghcr.io/your-user/screen-share:latest
```

## 4) Apply manifests to k3s

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## 5) Verify rollout

```bash
kubectl get pods -l app=screen-share
kubectl get svc screen-share
kubectl get ingress screen-share
```

## 6) Cloudflare Tunnel note

For this app, Cloudflare Tunnel can handle HTTP signaling (`/offer/*`), but WebRTC media may still require TURN for reliable public internet access.
