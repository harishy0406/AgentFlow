import re
from typing import Dict, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models import Project, ArtifactNode
from app.schemas import IacFile, IacBundleOut, IacCatalogOut


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", cleaned).strip("-") or "agentflow-app"


def _generate_terraform_aws(project_slug: str, app_name: str) -> List[IacFile]:
    main_tf = f"""terraform {{
  required_version = ">= 1.5.0"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
  backend "s3" {{
    bucket         = "{project_slug}-tf-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "{project_slug}-tf-locks"
    encrypt        = true
  }}
}}

provider "aws" {{
  region = var.aws_region
  default_tags {{
    tags = {{
      Application = "{app_name}"
      ManagedBy   = "AgentFlow-IaC"
      Environment = var.environment
    }}
  }}
}}

# VPC & Networking
module "vpc" {{
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "{project_slug}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${{var.aws_region}}a", "${{var.aws_region}}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = var.environment != "production" ? true : false
  enable_dns_hostnames = true
}}

# Security Groups
resource "aws_security_group" "alb" {{
  name        = "{project_slug}-alb-sg"
  description = "Public HTTP/HTTPS traffic to Application Load Balancer"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  ingress {{
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}

resource "aws_security_group" "ecs" {{
  name        = "{project_slug}-ecs-tasks-sg"
  description = "Ingress from ALB to ECS Fargate tasks"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}

# PostgreSQL RDS Instance
resource "aws_db_instance" "postgres" {{
  identifier             = "{project_slug}-db"
  engine                 = "postgres"
  engine_version         = "15.4"
  instance_class         = var.environment == "production" ? "db.t4g.medium" : "db.t4g.micro"
  allocated_storage      = 20
  max_allocated_storage  = 100
  db_name                = "{project_slug.replace('-', '_')}"
  username               = "appuser"
  password               = var.db_password
  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.ecs.id]
  skip_final_snapshot    = var.environment != "production"
  deletion_protection    = var.environment == "production"
}}

# ECS Fargate Service
resource "aws_ecs_cluster" "main" {{
  name = "{project_slug}-cluster"
}}

resource "aws_ecs_task_definition" "app" {{
  family                   = "{project_slug}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory

  container_definitions = jsonencode([
    {{
      name      = "{project_slug}-api"
      image     = var.container_image
      essential = true
      portMappings = [
        {{
          containerPort = 8000
          hostPort      = 8000
        }}
      ]
      environment = [
        {{
          name  = "ENVIRONMENT"
          value = var.environment
        }},
        {{
          name  = "DATABASE_URL"
          value = "postgresql://appuser:${{var.db_password}}@${{aws_db_instance.postgres.endpoint}}/{project_slug.replace('-', '_')}"
        }}
      ]
      logConfiguration = {{
        logDriver = "awslogs"
        options = {{
          "awslogs-group"         = "/ecs/{project_slug}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }}
      }}
    }}
  ])
}}
"""

    variables_tf = f"""variable "aws_region" {{
  description = "AWS deployment region"
  type        = string
  default     = "us-east-1"
}}

variable "environment" {{
  description = "Deployment environment (development, staging, production)"
  type        = string
  default     = "production"
}}

variable "container_image" {{
  description = "Docker image URI for {app_name}"
  type        = string
  default     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/{project_slug}:latest"
}}

variable "cpu" {{
  description = "ECS Task CPU units"
  type        = number
  default     = 512
}}

variable "memory" {{
  description = "ECS Task Memory in MB"
  type        = number
  default     = 1024
}}

variable "db_password" {{
  description = "Master password for PostgreSQL database"
  type        = string
  sensitive   = true
}}
"""

    outputs_tf = f"""output "vpc_id" {{
  description = "ID of the Provisioned VPC"
  value       = module.vpc.vpc_id
}}

output "rds_endpoint" {{
  description = "PostgreSQL DB connection endpoint"
  value       = aws_db_instance.postgres.endpoint
  sensitive   = false
}}

output "ecs_cluster_name" {{
  description = "ECS Cluster Name"
  value       = aws_ecs_cluster.main.name
}}
"""

    return [
        IacFile(path="terraform/aws/main.tf", content=main_tf, provider="aws", description="AWS VPC, RDS PostgreSQL, Security Groups, and ECS Fargate Cluster"),
        IacFile(path="terraform/aws/variables.tf", content=variables_tf, provider="aws", description="AWS Terraform variable declarations"),
        IacFile(path="terraform/aws/outputs.tf", content=outputs_tf, provider="aws", description="AWS Terraform output definitions"),
    ]


def _generate_terraform_gcp(project_slug: str, app_name: str) -> List[IacFile]:
    main_tf = f"""terraform {{
  required_version = ">= 1.5.0"
  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "~> 5.0"
    }}
  }}
}}

provider "google" {{
  project = var.project_id
  region  = var.region
}}

# Enable Required GCP APIs
resource "google_project_service" "services" {{
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}}

# Cloud SQL PostgreSQL Instance
resource "google_sql_database_instance" "postgres" {{
  name             = "{project_slug}-sql"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {{
    tier = var.environment == "production" ? "db-custom-2-7680" : "db-f1-micro"
    backup_configuration {{
      enabled = true
    }}
    ip_configuration {{
      ipv4_enabled = true
    }}
  }}
  deletion_protection = var.environment == "production"
}}

resource "google_sql_database" "app_db" {{
  name     = "{project_slug.replace('-', '_')}"
  instance = google_sql_database_instance.postgres.name
}}

resource "google_sql_user" "app_user" {{
  name     = "appuser"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}}

# Cloud Run Service (Serverless Container)
resource "google_cloud_run_v2_service" "app" {{
  name     = "{project_slug}-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {{
    containers {{
      image = var.container_image
      ports {{
        container_port = 8000
      }}
      env {{
        name  = "ENVIRONMENT"
        value = var.environment
      }}
      env {{
        name  = "DATABASE_URL"
        value = "postgresql://appuser:${{var.db_password}}@${{google_sql_database_instance.postgres.public_ip_address}}/{project_slug.replace('-', '_')}"
      }}
      resources {{
        limits = {{
          cpu    = "1000m"
          memory = "1Gi"
        }}
      }}
    }}
    scaling {{
      min_instance_count = var.environment == "production" ? 1 : 0
      max_instance_count = 10
    }}
  }}
}}

# Public Access IAM Policy
resource "google_cloud_run_v2_service_iam_member" "public_access" {{
  project  = google_cloud_run_v2_service.app.project
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}}
"""

    variables_tf = f"""variable "project_id" {{
  description = "Google Cloud Project ID"
  type        = string
}}

variable "region" {{
  description = "GCP deployment region"
  type        = string
  default     = "us-central1"
}}

variable "environment" {{
  description = "Environment tier (development, staging, production)"
  type        = string
  default     = "production"
}}

variable "container_image" {{
  description = "Container image URL on Artifact Registry or GCR"
  type        = string
  default     = "gcr.io/my-project/{project_slug}:latest"
}}

variable "db_password" {{
  description = "Master password for Cloud SQL PostgreSQL"
  type        = string
  sensitive   = true
}}
"""

    outputs_tf = f"""output "cloud_run_url" {{
  description = "Public HTTPS URL of deployed Cloud Run service"
  value       = google_cloud_run_v2_service.app.uri
}}

output "cloud_sql_ip" {{
  description = "Public IP Address of Cloud SQL Database"
  value       = google_sql_database_instance.postgres.public_ip_address
}}
"""

    return [
        IacFile(path="terraform/gcp/main.tf", content=main_tf, provider="gcp", description="GCP Cloud Run v2, Cloud SQL PostgreSQL, and IAM bindings"),
        IacFile(path="terraform/gcp/variables.tf", content=variables_tf, provider="gcp", description="GCP Terraform variable definitions"),
        IacFile(path="terraform/gcp/outputs.tf", content=outputs_tf, provider="gcp", description="GCP Terraform output definitions"),
    ]


def _generate_kubernetes_manifests(project_slug: str, app_name: str) -> List[IacFile]:
    deployment_yaml = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {project_slug}-deployment
  labels:
    app.kubernetes.io/name: {project_slug}
    app.kubernetes.io/instance: production
    app.kubernetes.io/managed-by: agentflow
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: {project_slug}
  template:
    metadata:
      labels:
        app: {project_slug}
    spec:
      containers:
      - name: api
        image: {project_slug}:latest
        imagePullPolicy: IfNotPresent
        ports:
        - name: http
          containerPort: 8000
        envFrom:
        - configMapRef:
            name: {project_slug}-config
        - secretRef:
            name: {project_slug}-secrets
        resources:
          requests:
            cpu: "250m"
            memory: "256Mi"
          limits:
            cpu: "1000m"
            memory: "1Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 2
          successThreshold: 1
"""

    service_yaml = f"""apiVersion: v1
kind: Service
metadata:
  name: {project_slug}-service
  labels:
    app: {project_slug}
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
    name: http
  selector:
    app: {project_slug}
"""

    ingress_yaml = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {project_slug}-ingress
  annotations:
    kubernetes.io/ingress.class: "nginx"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/proxy-body-size: "16m"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - {project_slug}.api.yourdomain.com
    secretName: {project_slug}-tls-cert
  rules:
  - host: {project_slug}.api.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {project_slug}-service
            port:
              number: 80
"""

    hpa_yaml = f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {project_slug}-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {project_slug}-deployment
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 75
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
"""

    configmap_yaml = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {project_slug}-config
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  PORT: "8000"
  ENABLE_METRICS: "true"
  PROJECT_NAME: "{app_name}"
"""

    return [
        IacFile(path="k8s/deployment.yaml", content=deployment_yaml, provider="kubernetes", description="Zero-downtime rolling update deployment with health probes"),
        IacFile(path="k8s/service.yaml", content=service_yaml, provider="kubernetes", description="Internal ClusterIP routing service"),
        IacFile(path="k8s/ingress.yaml", content=ingress_yaml, provider="kubernetes", description="NGINX Ingress Controller with auto TLS cert-manager configuration"),
        IacFile(path="k8s/hpa.yaml", content=hpa_yaml, provider="kubernetes", description="Horizontal Pod Autoscaler (CPU 75%, Memory 80%)"),
        IacFile(path="k8s/configmap.yaml", content=configmap_yaml, provider="kubernetes", description="Kubernetes ConfigMap for application environment parameters"),
    ]


def _generate_env_matrix(project_slug: str, app_name: str) -> List[IacFile]:
    prod_env = f"""# {app_name} - Production Environment Configuration
ENVIRONMENT=production
PORT=8000
DEBUG=false
LOG_LEVEL=INFO

# Database Configuration (Managed PostgreSQL)
DATABASE_URL=postgresql://appuser:STRONG_SECURE_PASSWORD@postgres.{project_slug}.internal:5432/{project_slug.replace('-', '_')}
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# Redis Cache & Background Tasks
REDIS_URL=redis://redis.{project_slug}.internal:6379/0

# Security & Authentication
SECRET_KEY=CHANGE_THIS_TO_A_64_CHAR_HEX_IN_PRODUCTION
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
ALLOWED_ORIGINS=https://{project_slug}.yourdomain.com,https://app.yourdomain.com

# OpenTelemetry Tracing & Monitoring
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.{project_slug}.internal:4317
OTEL_SERVICE_NAME={project_slug}-api
"""

    staging_env = f"""# {app_name} - Staging Environment Configuration
ENVIRONMENT=staging
PORT=8000
DEBUG=true
LOG_LEVEL=DEBUG

# Database Configuration
DATABASE_URL=postgresql://appuser:staging_pass@postgres-staging.{project_slug}.internal:5432/{project_slug.replace('-', '_')}_staging
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5

# Redis
REDIS_URL=redis://redis-staging.{project_slug}.internal:6379/0

# Security
SECRET_KEY=staging_secret_key_never_use_in_production
ALLOWED_ORIGINS=*
"""

    example_env = f"""# {app_name} - Local Development Template (.env.example)
ENVIRONMENT=development
PORT=8000
DEBUG=true
LOG_LEVEL=DEBUG

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/{project_slug.replace('-', '_')}_dev
REDIS_URL=redis://localhost:6379/0

SECRET_KEY=local_dev_secret_key_12345
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
"""

    return [
        IacFile(path="env/.env.production", content=prod_env, provider="env", description="Hardened production configuration template"),
        IacFile(path="env/.env.staging", content=staging_env, provider="env", description="Staging testing configuration template"),
        IacFile(path="env/.env.example", content=example_env, provider="env", description="Developer local setup documentation template"),
    ]


def generate_project_iac_bundle(project_id: str, provider: str, db: Session) -> IacBundleOut:
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    project_slug = _slugify(project.name)
    app_name = project.name

    norm_provider = provider.lower().strip()

    if norm_provider == "aws":
        files = _generate_terraform_aws(project_slug, app_name)
        steps = [
            "1. Configure AWS credentials via `aws configure` or assume an IAM role.",
            "2. Navigate to `terraform/aws` directory.",
            "3. Run `terraform init` to configure S3 backend and download AWS provider plugins.",
            "4. Run `terraform plan -var='db_password=YOUR_SECURE_PASSWORD'` to preview infrastructure graph.",
            "5. Run `terraform apply -auto-approve` to provision VPC, RDS, and ECS Fargate cluster."
        ]
    elif norm_provider == "gcp":
        files = _generate_terraform_gcp(project_slug, app_name)
        steps = [
            "1. Authenticate with Google Cloud using `gcloud auth application-default login`.",
            "2. Set active project: `gcloud config set project YOUR_PROJECT_ID`.",
            "3. Navigate to `terraform/gcp` directory.",
            "4. Run `terraform init` to download Google provider plugins.",
            "5. Run `terraform apply -var='project_id=YOUR_PROJECT_ID' -var='db_password=YOUR_PASSWORD'`."
        ]
    elif norm_provider in ("k8s", "kubernetes"):
        files = _generate_kubernetes_manifests(project_slug, app_name)
        norm_provider = "kubernetes"
        steps = [
            "1. Connect kubectl to target cluster: `kubectl config current-context`.",
            "2. Create Kubernetes namespace: `kubectl create namespace " + project_slug + "`.",
            "3. Create Secret for DB password: `kubectl create secret generic " + project_slug + "-secrets --from-literal=DATABASE_URL='...' -n " + project_slug + "`.",
            "4. Apply manifests: `kubectl apply -f k8s/ -n " + project_slug + "`.",
            "5. Verify rollout: `kubectl rollout status deployment/" + project_slug + "-deployment -n " + project_slug + "`."
        ]
    elif norm_provider == "env":
        files = _generate_env_matrix(project_slug, app_name)
        steps = [
            "1. Copy `env/.env.production` to your production host or secret manager.",
            "2. Replace all placeholder passwords and JWT secret keys.",
            "3. Inject into your container runtime or orchestration secret manager."
        ]
    else:
        raise ValueError(f"Unsupported IaC provider: '{provider}'. Must be 'aws', 'gcp', 'kubernetes', or 'env'")

    return IacBundleOut(
        project_id=project.id,
        project_name=project.name,
        provider=norm_provider,
        files=files,
        deployment_steps=steps
    )


def generate_all_iac_packages(project_id: str, db: Session) -> IacCatalogOut:
    target_id = UUID(project_id) if isinstance(project_id, str) else project_id
    project = db.query(Project).filter(Project.id == target_id).first()
    if not project:
        raise ValueError(f"Project with ID '{project_id}' not found")

    providers = ["aws", "gcp", "kubernetes", "env"]
    packages: Dict[str, IacBundleOut] = {}

    for prov in providers:
        packages[prov] = generate_project_iac_bundle(str(project.id), prov, db)

    return IacCatalogOut(
        project_id=project.id,
        project_name=project.name,
        available_providers=providers,
        packages=packages
    )
