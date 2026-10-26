# SmartSpend – Minikube Deployment Guide

## Prerequisites
- Windows 11 with **PowerShell**
- **Docker Desktop** (Docker driver for Minikube)
- **Minikube** installed (`minikube version` >= 1.33)
- **kubectl** installed and configured to talk to Minikube
- All six SmartSpend Docker images already loaded into Minikube (verified in audit)

## Directory layout
```
D:\SmartSpend\
│   docker-compose.yml   # existing compose (reference only)
│   k8s\                # <--- this folder contains all manifests
│       README.md        # you are reading this file
│       namespace.yaml
│       pv.yaml
│       pvc.yaml
│       frontend-configmap.yaml
│       expense-deployment.yaml
│       budget-deployment.yaml
│       analytics-deployment.yaml
│       alert-deployment.yaml
│       savings-deployment.yaml
│       frontend-deployment.yaml
```

## Step‑by‑step commands
Run each block in **PowerShell** from the `D:\SmartSpend` directory (or specify full paths as shown).

### 1. Create the `k8s` directory (if it does not exist)
```powershell
New-Item -ItemType Directory -Path "D:\SmartSpend\k8s" -Force
```

### 2. (Optional) Verify the audit results again
```powershell
# Minikube health
minikube status --format "Host: {{.Host}}`nKubelet: {{.Kubelet}}`nAPIServer: {{.APIServer}}`nKubeconfig: {{.Kubeconfig}}"

# Nodes
kubectl get nodes -o wide

# Existing pods (should be only system pods)
kubectl get pods -A -o wide
```

### 3. Validate all manifests (dry‑run)
```powershell
kubectl apply --dry-run=client -k "D:\SmartSpend\k8s"
```
- **Expected:** `configuration is valid` and no error messages.
- If you see errors, copy the output here and we’ll fix the YAML.

### 4. Deploy the full application
```powershell
kubectl apply -k "D:\SmartSpend\k8s"
```
- This creates the namespace, PVs, PVCs, ConfigMap, Deployments and Services.

### 5. Wait for all pods to become Ready
```powershell
kubectl wait --for=condition=Ready pod --all -n smartspend --timeout=180s
```
- If the command times out, run `kubectl get pods -n smartspend` to see which pod is stuck and share the logs (`kubectl logs <pod> -n smartspend`).

### 6. Verify services and obtain the frontend URL
```powershell
# List services – note the NodePort for the frontend (default 30080)
kubectl get svc -n smartspend

# Get Minikube IP (the address you will use in the browser)
$MINIKUBE_IP = minikube ip
Write-Host "Frontend URL: http://$MINIKUBE_IP:30080"
```
Open that URL in a browser. The React UI should load.

### 7. Test backend health endpoints (optional)
You can port‑forward a service temporarily to hit it from your host:
```powershell
# Example for expense‑service
kubectl port-forward svc/expense-service 8000:8000 -n smartspend
# In another PowerShell window:
curl http://localhost:8000/health
```
Repeat for `budget-service`, `analytics-service`, `alert-service`, `savings-service` (change the ports accordingly).

### 8. Verify SQLite persistence
```powershell
# Delete the expense‑service pod to force a restart
kubectl delete pod -l app=expense-service -n smartspend
# Wait for it to come back
kubectl wait --for=condition=Ready pod -l app=expense-service -n smartspend --timeout=60s

# Add a test record via the API (replace with your actual endpoint)
# Example using curl (adjust the payload as needed)
curl -X POST http://$MINIKUBE_IP:30080/api/expenses \
     -H "Content-Type: application/json" \
     -d '{"amount": 123.45, "category": "test", "date": "2026-10-26"}'

# Restart the pod again and query the list to ensure the record persisted
kubectl delete pod -l app=expense-service -n smartspend
kubectl wait --for=condition=Ready pod -l app=expense-service -n smartspend --timeout=60s
curl http://$MINIKUBE_IP:30080/api/expenses
```
If the previously created record is still present, persistence is working.

### 9. Common troubleshooting commands
| Issue | Command | What to look for |
|-------|---------|------------------|
| ImagePullBackOff | `kubectl describe pod <pod> -n smartspend` | Verify `Image: smartspend‑*` and `ImagePullPolicy: IfNotPresent` |
| CrashLoopBackOff | `kubectl logs <pod> -n smartspend` | Stack trace, missing env vars, DB permission errors |
| Pending (PVC) | `kubectl get pvc -n smartspend` and `kubectl describe pvc <pvc> -n smartspend` | Ensure the PVC is **Bound** to the hostPath PV |
| CORS errors in browser | Open DevTools → Network → look for `Access‑Control‑Allow‑Origin` header | Should contain `http://<minikube‑ip>:30080` or `*` as defined in `CORS_ALLOWED_ORIGINS` |
| Health probe failures | `kubectl describe pod <pod> -n smartspend` → Events | Check the `readinessProbe`/`livenessProbe` URLs and ports |

### 10. Stopping & restarting the cluster (data is retained)
```powershell
# Stop Minikube (keeps the hostPath data)
minikube stop

# Start Minikube again
minikube start --driver=docker

# Re‑apply manifests if anything was lost (usually not needed)
kubectl apply -k "D:\SmartSpend\k8s"
```

### 11. Updating an image (e.g., after a code change)
1. Re‑build the Docker image locally:
```powershell
docker build -t smartspend-expense-service:latest .\services\expense-service
```
2. Load it into Minikube (if not already present):
```powershell
minikube image load smartspend-expense-service:latest
```
3. Roll out the new image:
```powershell
kubectl rollout restart deployment/expense-service -n smartspend
```
   The PVC remains untouched, so the SQLite DB is preserved.

---
**That’s the complete command reference** for deploying SmartSpend on Minikube, verifying persistence, and troubleshooting common issues. Execute the steps in order, and let me know if any command fails or you need further assistance.
