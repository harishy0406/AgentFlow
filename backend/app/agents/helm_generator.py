"""
Kubernetes Helm 3 Chart Generator Engine for Microservices

Generates a production-grade, standard-compliant Helm 3 chart structure:
- Chart.yaml (v2 apiVersion)
- values.yaml with customizable replicas, images, ingress, resources, HPA, and probes
- templates/_helpers.tpl
- templates/deployment.yaml (with liveness/readiness probes, env vars, securityContext)
- templates/service.yaml
- templates/ingress.yaml
- templates/hpa.yaml
- templates/serviceaccount.yaml
- templates/configmap.yaml
- templates/secret.yaml
- templates/NOTES.txt
- .helmignore
"""

import io
import re
import zipfile
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

try:
    from ..models import Project, ArtifactNode
except ImportError:
    from app.models import Project, ArtifactNode


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", (text or "").lower())
    slug = re.sub(r"[-\s]+", "-", cleaned).strip("-")
    # Helm chart names must match [a-z0-9]([-a-z0-9]*[a-z0-9])?
    if not slug:
        return "agentflow-app"
    if not slug[0].isalnum():
        slug = f"app-{slug}"
    return slug[:50]


def build_helm_chart_files(
    app_name: str,
    project_slug: str,
    description: str = "",
    replica_count: int = 2,
    service_port: int = 8000,
    domain: Optional[str] = None,
) -> Dict[str, str]:
    """
    Builds the complete dictionary of file paths to content strings for a Helm chart.
    """
    slug = _slugify(project_slug or app_name)
    host = domain or f"{slug}.agentflow.internal"
    clean_desc = (description or f"Helm chart for {app_name} microservice").replace('"', '\\"')

    chart_yaml = f"""apiVersion: v2
name: {slug}
description: "{clean_desc}"
type: application
version: 0.1.0
appVersion: "1.0.0"
maintainers:
  - name: AgentFlow Platform Engineering
    email: devops@agentflow.io
"""

    values_yaml = f"""# Default values for {slug}.
# This is a YAML-formatted file.
# Declare variables to be passed into your templates.

replicaCount: {replica_count}

image:
  repository: agentflow/{slug}
  pullPolicy: IfNotPresent
  # Overrides the image tag whose default is the chart appVersion.
  tag: ""

imagePullSecrets: []
nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  automount: true
  annotations: {{}}
  name: ""

podAnnotations: {{}}
podLabels: {{}}

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 10001
  fsGroup: 10001

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: false
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: {service_port}
  targetPort: {service_port}
  protocol: TCP

ingress:
  enabled: true
  className: "nginx"
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: {host}
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: {slug}-tls
      hosts:
        - {host}

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi

autoscaling:
  enabled: true
  minReplicas: {max(1, replica_count)}
  maxReplicas: 10
  targetCPUUtilizationPercentage: 80
  targetMemoryUtilizationPercentage: 80

livenessProbe:
  httpGet:
    path: /api/v1/health
    port: http
  initialDelaySeconds: 15
  periodSeconds: 20
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /api/v1/health
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 2

env:
  ENVIRONMENT: "production"
  PORT: "{service_port}"
  LOG_LEVEL: "info"

secretEnv:
  DATABASE_URL: "postgresql://user:secret@postgres-svc:5432/{slug}"
  JWT_SECRET: "change-in-production-vault"

nodeSelector: {{}}
tolerations: []
affinity: {{}}
"""

    helpers_tpl = f"""{{{{/*
Expand the name of the chart.
*/}}}}
{{{{- define "{slug}.name" -}}}}
{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{{{/*
Create a default fully qualified app name.
*/}}}}
{{{{- define "{slug}.fullname" -}}}}
{{{{- if .Values.fullnameOverride }}}}
{{{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- $name := default .Chart.Name .Values.nameOverride }}}}
{{{{- if contains $name .Release.Name }}}}
{{{{- .Release.Name | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}
{{{{- end }}}}
{{{{- end }}}}

{{{{/*
Create chart name and version as used by the chart label.
*/}}}}
{{{{- define "{slug}.chart" -}}}}
{{{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{{{/*
Common labels
*/}}}}
{{{{- define "{slug}.labels" -}}}}
helm.sh/chart: {{{{ include "{slug}.chart" . }}}}
{{{{ include "{slug}.selectorLabels" . }}}}
{{{{- if .Chart.AppVersion }}}}
app.kubernetes.io/version: {{{{ .Chart.AppVersion | quote }}}}
{{{{- end }}}}
app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
{{{{- end }}}}

{{{{/*
Selector labels
*/}}}}
{{{{- define "{slug}.selectorLabels" -}}}}
app.kubernetes.io/name: {{{{ include "{slug}.name" . }}}}
app.kubernetes.io/instance: {{{{ .Release.Name }}}}
{{{{- end }}}}
"""

    deployment_yaml = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{{{ include "{slug}.fullname" . }}}}
  labels:
    {{{{- include "{slug}.labels" . | nindent 4 }}}}
spec:
  {{{{- if not .Values.autoscaling.enabled }}}}
  replicas: {{{{ .Values.replicaCount }}}}
  {{{{- end }}}}
  selector:
    matchLabels:
      {{{{- include "{slug}.selectorLabels" . | nindent 6 }}}}
  template:
    metadata:
      annotations:
        checksum/config: {{{{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}}}
        checksum/secret: {{{{ include (print $.Template.BasePath "/secret.yaml") . | sha256sum }}}}
        {{{{- with .Values.podAnnotations }}}}
        {{{{- toYaml . | nindent 8 }}}}
        {{{{- end }}}}
      labels:
        {{{{- include "{slug}.labels" . | nindent 8 }}}}
        {{{{- with .Values.podLabels }}}}
        {{{{- toYaml . | nindent 8 }}}}
        {{{{- end }}}}
    spec:
      {{{{- with .Values.imagePullSecrets }}}}
      imagePullSecrets:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      serviceAccountName: {{{{ include "{slug}.fullname" . }}}}
      securityContext:
        {{{{- toYaml .Values.podSecurityContext | nindent 8 }}}}
      containers:
        - name: {{{{ .Chart.Name }}}}
          securityContext:
            {{{{- toYaml .Values.securityContext | nindent 12 }}}}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag | default .Chart.AppVersion }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          ports:
            - name: http
              containerPort: {{{{ .Values.service.port }}}}
              protocol: {{{{ .Values.service.protocol }}}}
          envFrom:
            - configMapRef:
                name: {{{{ include "{slug}.fullname" . }}}}-config
            - secretRef:
                name: {{{{ include "{slug}.fullname" . }}}}-secret
          livenessProbe:
            {{{{- toYaml .Values.livenessProbe | nindent 12 }}}}
          readinessProbe:
            {{{{- toYaml .Values.readinessProbe | nindent 12 }}}}
          resources:
            {{{{- toYaml .Values.resources | nindent 12 }}}}
      {{{{- with .Values.nodeSelector }}}}
      nodeSelector:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      {{{{- with .Values.affinity }}}}
      affinity:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
      {{{{- with .Values.tolerations }}}}
      tolerations:
        {{{{- toYaml . | nindent 8 }}}}
      {{{{- end }}}}
"""

    service_yaml = f"""apiVersion: v1
kind: Service
metadata:
  name: {{{{ include "{slug}.fullname" . }}}}
  labels:
    {{{{- include "{slug}.labels" . | nindent 4 }}}}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: {{{{ .Values.service.targetPort }}}}
      protocol: {{{{ .Values.service.protocol }}}}
      name: http
  selector:
    {{{{- include "{slug}.selectorLabels" . | nindent 4 }}}}
"""

    ingress_yaml = f"""{{{{- if .Values.ingress.enabled -}}}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{{{ include "{slug}.fullname" . }}}}
  labels:
    {{{{- include "{slug}.labels" . | nindent 4 }}}}
  {{{{- with .Values.ingress.annotations }}}}
  annotations:
    {{{{- toYaml . | nindent 4 }}}}
  {{{{- end }}}}
spec:
  {{{{- if .Values.ingress.className }}}}
  ingressClassName: {{{{ .Values.ingress.className }}}}
  {{{{- end }}}}
  {{{{- if .Values.ingress.tls }}}}
  tls:
    {{{{- range .Values.ingress.tls }}}}
    - hosts:
        {{{{- range .hosts }}}}
        - {{{{ . | quote }}}}
        {{{{- end }}}}
      secretName: {{{{ .secretName }}}}
    {{{{- end }}}}
  {{{{- end }}}}
  rules:
    {{{{- range .Values.ingress.hosts }}}}
    - host: {{{{ .host | quote }}}}
      http:
        paths:
          {{{{- range .paths }}}}
          - path: {{{{ .path }}}}
            pathType: {{{{ .pathType }}}}
            backend:
              service:
                name: {{{{ include "{slug}.fullname" $ }}}}
                port:
                  number: {{{{ $.Values.service.port }}}}
          {{{{- end }}}}
    {{{{- end }}}}
{{{{- end }}}}
"""

    hpa_yaml = f"""{{{{- if .Values.autoscaling.enabled }}}}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{{{ include "{slug}.fullname" . }}}}
  labels:
    {{{{- include "{slug}.labels" . | nindent 4 }}}}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{{{ include "{slug}.fullname" . }}}}
  minReplicas: {{{{ .Values.autoscaling.minReplicas }}}}
  maxReplicas: {{{{ .Values.autoscaling.maxReplicas }}}}
  metrics:
    {{{{- if .Values.autoscaling.targetCPUUtilizationPercentage }}}}
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetCPUUtilizationPercentage }}}}
    {{{{- end }}}}
    {{{{- if .Values.autoscaling.targetMemoryUtilizationPercentage }}}}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetMemoryUtilizationPercentage }}}}
    {{{{- end }}}}
{{{{- end }}}}
"""

    configmap_yaml = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {{{{ include "{slug}.fullname" . }}}}-config
  labels:
    {{{{- include "{slug}.labels" . | nindent 4 }}}}
data:
  {{{{- range $key, $val := .Values.env }}}}
  {{{{ $key }}}}: {{{{ $val | quote }}}}
  {{{{- end }}}}
"""

    secret_yaml = f"""apiVersion: v1
kind: Secret
metadata:
  name: {{{{ include "{slug}.fullname" . }}}}-secret
  labels:
    {{{{- include "{slug}.labels" . | nindent 4 }}}}
type: Opaque
stringData:
  {{{{- range $key, $val := .Values.secretEnv }}}}
  {{{{ $key }}}}: {{{{ $val | quote }}}}
  {{{{- end }}}}
"""

    serviceaccount_yaml = f"""{{{{- if .Values.serviceAccount.create -}}}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{{{ include "{slug}.fullname" . }}}}
  labels:
    {{{{- include "{slug}.labels" . | nindent 4 }}}}
  {{{{- with .Values.serviceAccount.annotations }}}}
  annotations:
    {{{{- toYaml . | nindent 4 }}}}
  {{{{- end }}}}
automountServiceAccountToken: {{{{ .Values.serviceAccount.automount }}}}
{{{{- end }}}}
"""

    notes_txt = f"""1. Get the application URL by running these commands:
{{{{- if .Values.ingress.enabled }}}}
{{{{- range $host := .Values.ingress.hosts }}}}
  https://{{{{ $host.host }}}}
{{{{- end }}}}
{{{{- else if contains "NodePort" .Values.service.type }}}}
  export NODE_PORT=$(kubectl get --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{.spec.ports[0].nodePort}}" services {{{{ include "{slug}.fullname" . }}}})
  export NODE_IP=$(kubectl get nodes --namespace {{{{ .Release.Namespace }}}} -o jsonpath="{{.items[0].status.addresses[0].address}}")
  echo http://$NODE_IP:$NODE_PORT
{{{{- else if contains "LoadBalancer" .Values.service.type }}}}
     NOTE: It may take a few minutes for the LoadBalancer IP to be available.
           You can watch the status of by running 'kubectl get --namespace {{{{ .Release.Namespace }}}} svc -w {{{{ include "{slug}.fullname" . }}}}'
  export SERVICE_IP=$(kubectl get svc --namespace {{{{ .Release.Namespace }}}} {{{{ include "{slug}.fullname" . }}}} --template "{{{{ range (index .status.loadBalancer.ingress 0) }}}}{{{{.}}}}{{{{ end }}}}")
  echo http://$SERVICE_IP:{{{{ .Values.service.port }}}}
{{{{- else if contains "ClusterIP" .Values.service.type }}}}
  export POD_NAME=$(kubectl get pods --namespace {{{{ .Release.Namespace }}}} -l "{{{{ include "{slug}.selectorLabels" . }}}}" -o jsonpath="{{.items[0].metadata.name}}")
  echo "Visit http://127.0.0.1:8080 to use your application"
  kubectl --namespace {{{{ .Release.Namespace }}}} port-forward $POD_NAME 8080:{{{{ .Values.service.port }}}}
{{{{- end }}}}
"""

    helmignore = """.git/
.gitignore
*.swp
*.bak
*.tmp
*~
.DS_Store
.project
.idea/
"""

    return {
        f"{slug}/Chart.yaml": chart_yaml,
        f"{slug}/values.yaml": values_yaml,
        f"{slug}/templates/_helpers.tpl": helpers_tpl,
        f"{slug}/templates/deployment.yaml": deployment_yaml,
        f"{slug}/templates/service.yaml": service_yaml,
        f"{slug}/templates/ingress.yaml": ingress_yaml,
        f"{slug}/templates/hpa.yaml": hpa_yaml,
        f"{slug}/templates/configmap.yaml": configmap_yaml,
        f"{slug}/templates/secret.yaml": secret_yaml,
        f"{slug}/templates/serviceaccount.yaml": serviceaccount_yaml,
        f"{slug}/templates/NOTES.txt": notes_txt,
        f"{slug}/.helmignore": helmignore,
    }


def generate_helm_chart_bundle(
    project_id: UUID,
    db: Session,
    replica_count: int = 2,
    service_port: int = 8000,
) -> Dict[str, Any]:
    """
    Fetches the project metadata and generates the full Helm 3 chart bundle dictionary.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    slug = _slugify(project.name)
    files = build_helm_chart_files(
        app_name=project.name,
        project_slug=slug,
        description=project.brief or "",
        replica_count=replica_count,
        service_port=service_port,
    )

    return {
        "project_id": str(project.id),
        "project_name": project.name,
        "chart_name": slug,
        "version": "0.1.0",
        "app_version": "1.0.0",
        "file_count": len(files),
        "files": files,
        "deployment_steps": [
            f"helm repo add stable https://charts.helm.sh/stable || true",
            f"helm lint ./{slug}",
            f"helm upgrade --install {slug} ./{slug} --namespace {slug} --create-namespace",
            f"kubectl get pods -n {slug} -l app.kubernetes.io/name={slug}",
        ],
    }


def generate_helm_chart_zip(bundle: Dict[str, Any]) -> bytes:
    """
    Packs all files in the Helm chart bundle into an in-memory ZIP archive.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path, content in bundle.get("files", {}).items():
            zf.writestr(file_path, content)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()
