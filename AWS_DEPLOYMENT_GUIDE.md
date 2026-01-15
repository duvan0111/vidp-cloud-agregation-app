# 🚀 Guide de Déploiement AWS - Video Aggregation Service

Ce guide détaille le déploiement du microservice `app_agregation` sur Amazon Web Services (AWS).

---

## 📋 Table des matières

- [Architecture AWS](#architecture-aws)
- [Prérequis](#prérequis)
- [Étape 1 : Configuration IAM](#étape-1--configuration-iam)
- [Étape 2 : Configuration S3](#étape-2--configuration-s3)
- [Étape 3 : Configuration MongoDB](#étape-3--configuration-mongodb)
- [Étape 4 : Build et Push Docker](#étape-4--build-et-push-docker)
- [Étape 5 : Déploiement ECS](#étape-5--déploiement-ecs)
- [Étape 6 : Configuration ALB](#étape-6--configuration-alb)
- [Étape 7 : Monitoring](#étape-7--monitoring)
- [Étape 8 : CI/CD](#étape-8--cicd)

---

## 🏗 Architecture AWS

```
┌─────────────────────────────────────────────────────────────────┐
│                          AWS REGION (us-east-1)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  VPC (10.0.0.0/16)                                     │   │
│  │                                                        │   │
│  │  ┌─────────────────────────────────────────────┐      │   │
│  │  │  Public Subnet (10.0.1.0/24)                │      │   │
│  │  │                                              │      │   │
│  │  │  ┌─────────────────────────────────────┐    │      │   │
│  │  │  │  Application Load Balancer (ALB)    │    │      │   │
│  │  │  │  - Port 80 (HTTP)                   │    │      │   │
│  │  │  │  - Port 443 (HTTPS)                 │    │      │   │
│  │  │  └──────────┬──────────────────────────┘    │      │   │
│  │  │             │                                │      │   │
│  │  └─────────────┼────────────────────────────────┘      │   │
│  │                │                                        │   │
│  │  ┌─────────────┼────────────────────────────────┐      │   │
│  │  │  Private Subnet (10.0.2.0/24)          │      │      │   │
│  │  │             │                           │      │      │   │
│  │  │  ┌──────────▼───────────────────────┐  │      │      │   │
│  │  │  │  ECS Cluster (Fargate)           │  │      │      │   │
│  │  │  │                                   │  │      │      │   │
│  │  │  │  ┌─────────────────────────────┐ │  │      │      │   │
│  │  │  │  │ Service: app_agregation     │ │  │      │      │   │
│  │  │  │  │                              │ │  │      │      │   │
│  │  │  │  │  ┌──────────────────────┐   │ │  │      │      │   │
│  │  │  │  │  │ Task 1 (Container)   │   │ │  │      │      │   │
│  │  │  │  │  │ - CPU: 1 vCPU        │   │ │  │      │      │   │
│  │  │  │  │  │ - Memory: 2GB        │   │ │  │      │      │   │
│  │  │  │  │  │ - Port: 8000         │   │ │  │      │      │   │
│  │  │  │  │  └──────────────────────┘   │ │  │      │      │   │
│  │  │  │  │                              │ │  │      │      │   │
│  │  │  │  │  ┌──────────────────────┐   │ │  │      │      │   │
│  │  │  │  │  │ Task 2 (Container)   │   │ │  │      │      │   │
│  │  │  │  │  └──────────────────────┘   │ │  │      │      │   │
│  │  │  │  │                              │ │  │      │      │   │
│  │  │  │  │  ┌──────────────────────┐   │ │  │      │      │   │
│  │  │  │  │  │ Task N (Auto-scaled) │   │ │  │      │      │   │
│  │  │  │  │  └──────────────────────┘   │ │  │      │      │   │
│  │  │  │  └─────────────────────────────┘ │  │      │      │   │
│  │  │  └───────────────────────────────────┘  │      │      │   │
│  │  └────────────────────────────────────────┘      │      │   │
│  └────────────────────────────────────────────────┘      │   │
│                                                           │   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Amazon S3                                            │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │  Bucket: vidp-video-storage                     │  │   │
│  │  │  - /videos/     (Vidéos finales)                │  │   │
│  │  │  - /temp/       (Fichiers temporaires)          │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                           │   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Amazon DocumentDB / MongoDB Atlas                   │   │
│  │  - Database: vidp_cloud_db                           │   │
│  │  - Collection: videos                                │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                           │   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  AWS Secrets Manager                                  │   │
│  │  - vidp/mongodb-url                                   │   │
│  │  - vidp/aws-credentials                               │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                           │   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Amazon CloudWatch                                    │   │
│  │  - Logs: /ecs/vidp-aggregation                        │   │
│  │  - Metrics: CPU, Memory, Requests                     │   │
│  │  - Alarms: High CPU, Error Rate                       │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                           │   │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  Amazon ECR (Elastic Container Registry)              │   │
│  │  - Repository: vidp-aggregation                       │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                           │   │
└───────────────────────────────────────────────────────────────┘
```

---

## 📦 Prérequis

### Outils nécessaires

```bash
# AWS CLI
aws --version  # >= 2.0

# Docker
docker --version  # >= 20.10

# jq (pour parser JSON)
jq --version
```

### Installation AWS CLI

```bash
# Linux
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# macOS
brew install awscli

# Configuration
aws configure
# AWS Access Key ID: <your-key>
# AWS Secret Access Key: <your-secret>
# Default region name: us-east-1
# Default output format: json
```

---

## 🔐 Étape 1 : Configuration IAM

### 1.1 Créer une politique IAM pour ECS

**Fichier** : `iam-policy-ecs-task.json`

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::vidp-video-storage",
        "arn:aws:s3:::vidp-video-storage/*"
      ]
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:vidp/*"
    }
  ]
}
```

**Créer la politique** :

```bash
aws iam create-policy \
  --policy-name VidpAggregationTaskPolicy \
  --policy-document file://iam-policy-ecs-task.json
```

### 1.2 Créer un rôle IAM pour les tâches ECS

```bash
# 1. Trust policy
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# 2. Créer le rôle
aws iam create-role \
  --role-name vidpAggregationTaskRole \
  --assume-role-policy-document file://trust-policy.json

# 3. Attacher la politique
aws iam attach-role-policy \
  --role-name vidpAggregationTaskRole \
  --policy-arn arn:aws:iam::<account-id>:policy/VidpAggregationTaskPolicy
```

### 1.3 Créer un rôle d'exécution ECS

```bash
# Rôle standard AWS
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

---

## 🪣 Étape 2 : Configuration S3

### 2.1 Créer le bucket S3

```bash
# Créer le bucket
aws s3 mb s3://vidp-video-storage --region us-east-1

# Bloquer l'accès public (sécurité)
aws s3api put-public-access-block \
  --bucket vidp-video-storage \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Activer le versioning
aws s3api put-bucket-versioning \
  --bucket vidp-video-storage \
  --versioning-configuration Status=Enabled

# Activer le chiffrement
aws s3api put-bucket-encryption \
  --bucket vidp-video-storage \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

### 2.2 Configurer la lifecycle policy

**Fichier** : `s3-lifecycle-policy.json`

```json
{
  "Rules": [
    {
      "Id": "DeleteTempFiles",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "temp/"
      },
      "Expiration": {
        "Days": 1
      }
    },
    {
      "Id": "ArchiveOldVideos",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "videos/"
      },
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
```

**Appliquer la policy** :

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket vidp-video-storage \
  --lifecycle-configuration file://s3-lifecycle-policy.json
```

### 2.3 Créer la structure de dossiers

```bash
# Créer les dossiers (S3 les crée implicitement)
aws s3api put-object --bucket vidp-video-storage --key videos/
aws s3api put-object --bucket vidp-video-storage --key temp/
```

---

## 🗄️ Étape 3 : Configuration MongoDB

### Option A : MongoDB Atlas (Recommandé)

1. **Créer un cluster** sur [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. **Créer un utilisateur** avec accès lecture/écriture
3. **Ajouter une IP Whitelist** : `0.0.0.0/0` (ou VPC CIDR)
4. **Récupérer la connection string** :
   ```
   mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/vidp_cloud_db
   ```

### Option B : Amazon DocumentDB

```bash
# Créer un cluster DocumentDB
aws docdb create-db-cluster \
  --db-cluster-identifier vidp-docdb-cluster \
  --engine docdb \
  --master-username admin \
  --master-user-password <your-password> \
  --vpc-security-group-ids sg-xxxxx \
  --db-subnet-group-name vidp-subnet-group

# Créer une instance
aws docdb create-db-instance \
  --db-instance-identifier vidp-docdb-instance \
  --db-instance-class db.r5.large \
  --engine docdb \
  --db-cluster-identifier vidp-docdb-cluster

# Récupérer l'endpoint
aws docdb describe-db-clusters \
  --db-cluster-identifier vidp-docdb-cluster \
  --query 'DBClusters[0].Endpoint' \
  --output text
```

### Stocker les credentials dans Secrets Manager

```bash
# Créer le secret
aws secretsmanager create-secret \
  --name vidp/mongodb-url \
  --description "MongoDB connection URL for VidP" \
  --secret-string "mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/vidp_cloud_db"

# Récupérer le secret (test)
aws secretsmanager get-secret-value \
  --secret-id vidp/mongodb-url \
  --query 'SecretString' \
  --output text
```

---

## 🐳 Étape 4 : Build et Push Docker

### 4.1 Créer un repository ECR

```bash
# Créer le repository
aws ecr create-repository \
  --repository-name vidp-aggregation \
  --region us-east-1

# Récupérer l'URI
ECR_URI=$(aws ecr describe-repositories \
  --repository-names vidp-aggregation \
  --query 'repositories[0].repositoryUri' \
  --output text)

echo "ECR URI: $ECR_URI"
```

### 4.2 Build l'image Docker

**Créez un `Dockerfile`** :

```dockerfile
FROM python:3.10-slim

# Installer FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier et installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Créer les répertoires
RUN mkdir -p /app/video_storage /app/temp

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# Lancer l'application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**Build l'image** :

```bash
# Build
docker build -t vidp-aggregation:latest .

# Test local (optionnel)
docker run -d -p 8000:8000 \
  -e MONGODB_URL="mongodb://localhost:27017" \
  -e API_URL="http://localhost:8000" \
  vidp-aggregation:latest

# Tester
curl http://localhost:8000/api/health
```

### 4.3 Push vers ECR

```bash
# Authentification ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_URI

# Tag l'image
docker tag vidp-aggregation:latest $ECR_URI:latest
docker tag vidp-aggregation:latest $ECR_URI:v1.0.0

# Push
docker push $ECR_URI:latest
docker push $ECR_URI:v1.0.0
```

---

## 🚀 Étape 5 : Déploiement ECS

### 5.1 Créer un cluster ECS

```bash
# Créer le cluster (Fargate)
aws ecs create-cluster \
  --cluster-name vidp-cluster \
  --capacity-providers FARGATE FARGATE_SPOT \
  --default-capacity-provider-strategy \
    capacityProvider=FARGATE,weight=1 \
    capacityProvider=FARGATE_SPOT,weight=1
```

### 5.2 Créer une Task Definition

**Fichier** : `ecs-task-definition.json`

```json
{
  "family": "vidp-aggregation",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::<account-id>:role/vidpAggregationTaskRole",
  "containerDefinitions": [
    {
      "name": "aggregation-container",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/vidp-aggregation:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "HOST", "value": "0.0.0.0"},
        {"name": "PORT", "value": "8000"},
        {"name": "API_URL", "value": "https://api.vidp.example.com"},
        {"name": "USE_S3_STORAGE", "value": "true"},
        {"name": "AWS_S3_BUCKET", "value": "vidp-video-storage"},
        {"name": "AWS_REGION", "value": "us-east-1"},
        {"name": "SUBTITLE_SERVICE_URL", "value": "http://app-subtitle.local:8002/api/generate-subtitles/"},
        {"name": "MONGODB_DATABASE", "value": "vidp_cloud_db"},
        {"name": "MONGODB_COLLECTION", "value": "videos"},
        {"name": "LOG_LEVEL", "value": "INFO"}
      ],
      "secrets": [
        {
          "name": "MONGODB_URL",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:<account-id>:secret:vidp/mongodb-url"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/vidp-aggregation",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

**Enregistrer la task** :

```bash
# Créer le log group d'abord
aws logs create-log-group --log-group-name /ecs/vidp-aggregation

# Enregistrer la task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
```

### 5.3 Créer le service ECS

```bash
# Créer le service
aws ecs create-service \
  --cluster vidp-cluster \
  --service-name aggregation-service \
  --task-definition vidp-aggregation \
  --desired-count 2 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxxxx,subnet-yyyyy],
    securityGroups=[sg-zzzzz],
    assignPublicIp=ENABLED
  }" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:<account-id>:targetgroup/vidp-aggregation-tg/xxxxx,containerName=aggregation-container,containerPort=8000" \
  --health-check-grace-period-seconds 60

# Vérifier le statut
aws ecs describe-services \
  --cluster vidp-cluster \
  --services aggregation-service \
  --query 'services[0].{Status:status,RunningCount:runningCount,DesiredCount:desiredCount}'
```

---

## ⚖️ Étape 6 : Configuration ALB

### 6.1 Créer un Application Load Balancer

```bash
# Créer le security group pour l'ALB
aws ec2 create-security-group \
  --group-name vidp-alb-sg \
  --description "Security group for VidP ALB" \
  --vpc-id vpc-xxxxx

# Autoriser HTTP/HTTPS
aws ec2 authorize-security-group-ingress \
  --group-id sg-alb-xxxxx \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id sg-alb-xxxxx \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# Créer l'ALB
aws elbv2 create-load-balancer \
  --name vidp-alb \
  --subnets subnet-xxxxx subnet-yyyyy \
  --security-groups sg-alb-xxxxx \
  --scheme internet-facing \
  --type application \
  --ip-address-type ipv4
```

### 6.2 Créer un Target Group

```bash
# Créer le target group
aws elbv2 create-target-group \
  --name vidp-aggregation-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id vpc-xxxxx \
  --target-type ip \
  --health-check-enabled \
  --health-check-path /api/health \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --matcher HttpCode=200
```

### 6.3 Créer un Listener

```bash
# Listener HTTP
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...

# Listener HTTPS (avec certificat ACM)
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:... \
  --ssl-policy ELBSecurityPolicy-TLS-1-2-2017-01 \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...
```

---

## 📊 Étape 7 : Monitoring

### 7.1 CloudWatch Logs Insights

Exemples de requêtes :

```sql
-- Erreurs 5xx
fields @timestamp, @message
| filter @message like /ERROR/
| sort @timestamp desc
| limit 100

-- Durée de traitement
fields @timestamp, duration
| stats avg(duration), max(duration), min(duration) by bin(5m)

-- Top des endpoints appelés
fields @timestamp, request_path
| stats count() as request_count by request_path
| sort request_count desc
```

### 7.2 Créer des Alarmes CloudWatch

**CPU élevé** :

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name vidp-aggregation-high-cpu \
  --alarm-description "Alerte si CPU > 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=ServiceName,Value=aggregation-service Name=ClusterName,Value=vidp-cluster \
  --alarm-actions arn:aws:sns:us-east-1:<account-id>:vidp-alerts
```

**Taux d'erreur élevé** :

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name vidp-aggregation-high-error-rate \
  --alarm-description "Alerte si taux d'erreur > 5%" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 60 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 3 \
  --dimensions Name=TargetGroup,Value=targetgroup/vidp-aggregation-tg/xxxxx \
  --alarm-actions arn:aws:sns:us-east-1:<account-id>:vidp-alerts
```

### 7.3 Créer un Dashboard CloudWatch

```bash
aws cloudwatch put-dashboard \
  --dashboard-name VidP-Aggregation \
  --dashboard-body file://cloudwatch-dashboard.json
```

**Fichier** : `cloudwatch-dashboard.json` (exemple simplifié)

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ECS", "CPUUtilization", {"stat": "Average"}]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "CPU Utilization"
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/ApplicationELB", "RequestCount", {"stat": "Sum"}]
        ],
        "period": 60,
        "stat": "Sum",
        "region": "us-east-1",
        "title": "Request Count"
      }
    }
  ]
}
```

---

## 🔄 Étape 8 : CI/CD

### 8.1 GitHub Actions Workflow

**Fichier** : `.github/workflows/deploy.yml`

```yaml
name: Deploy to AWS ECS

on:
  push:
    branches: [main]
    paths:
      - 'app_agregation/**'

env:
  AWS_REGION: us-east-1
  ECR_REPOSITORY: vidp-aggregation
  ECS_CLUSTER: vidp-cluster
  ECS_SERVICE: aggregation-service
  CONTAINER_NAME: aggregation-container

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}
      
      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v1
      
      - name: Build, tag, and push image to Amazon ECR
        id: build-image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          cd app_agregation
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          echo "image=$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" >> $GITHUB_OUTPUT
      
      - name: Update ECS service
        run: |
          aws ecs update-service \
            --cluster ${{ env.ECS_CLUSTER }} \
            --service ${{ env.ECS_SERVICE }} \
            --force-new-deployment
      
      - name: Wait for service stability
        run: |
          aws ecs wait services-stable \
            --cluster ${{ env.ECS_CLUSTER }} \
            --services ${{ env.ECS_SERVICE }}
```

### 8.2 AWS CodePipeline (Alternative)

```bash
# Créer un pipeline CodePipeline
aws codepipeline create-pipeline --cli-input-json file://pipeline-config.json
```

---

## ✅ Checklist de Déploiement

### Pré-déploiement
- [ ] IAM roles et policies créés
- [ ] S3 bucket configuré avec lifecycle
- [ ] MongoDB (Atlas ou DocumentDB) configuré
- [ ] Secrets stockés dans Secrets Manager
- [ ] ECR repository créé
- [ ] Image Docker buildée et pushée

### Déploiement
- [ ] ECS cluster créé
- [ ] Task definition enregistrée
- [ ] Service ECS créé avec 2+ instances
- [ ] ALB et Target Group configurés
- [ ] Security groups configurés
- [ ] DNS/Route53 pointant vers ALB

### Post-déploiement
- [ ] Health checks passent (ALB + ECS)
- [ ] CloudWatch Logs fonctionnent
- [ ] Alarmes CloudWatch configurées
- [ ] Dashboard CloudWatch créé
- [ ] Tests fonctionnels réussis
- [ ] CI/CD pipeline configuré

---

## 🧪 Tests de Validation

### Test 1 : Health Check

```bash
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names vidp-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text)

curl http://$ALB_DNS/api/health
```

### Test 2 : Upload et Traitement

```bash
curl -X POST "http://$ALB_DNS/api/process-video/" \
  -F "video=@test.mp4" \
  -F "srt_file=@subtitles.srt" \
  -F "resolution=720p"
```

### Test 3 : Streaming

```bash
# Récupérer un video_id depuis MongoDB
VIDEO_ID="65f1234567890abcdef12345"

# Tester le streaming
curl -I "http://$ALB_DNS/api/stream/$VIDEO_ID"
```

---

## 📞 Support

### Logs CloudWatch

```bash
# Tail des logs en temps réel
aws logs tail /ecs/vidp-aggregation --follow

# Rechercher des erreurs
aws logs filter-log-events \
  --log-group-name /ecs/vidp-aggregation \
  --filter-pattern "ERROR" \
  --start-time $(date -u -d '1 hour ago' +%s)000
```

### Debugging ECS

```bash
# Lister les tâches
aws ecs list-tasks --cluster vidp-cluster --service-name aggregation-service

# Décrire une tâche
aws ecs describe-tasks --cluster vidp-cluster --tasks <task-arn>

# Exécuter une commande dans un conteneur
aws ecs execute-command \
  --cluster vidp-cluster \
  --task <task-id> \
  --container aggregation-container \
  --interactive \
  --command "/bin/bash"
```

---

**Déploiement AWS complet et prêt pour la production !** ☁️🚀
