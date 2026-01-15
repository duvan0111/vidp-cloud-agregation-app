# 🎬 Video Aggregation Service

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![DynamoDB](https://img.shields.io/badge/DynamoDB-AWS-4053D6.svg?style=flat&logo=amazon-dynamodb&logoColor=white)](https://aws.amazon.com/dynamodb/)
[![S3](https://img.shields.io/badge/S3-AWS-569A31.svg?style=flat&logo=amazon-s3&logoColor=white)](https://aws.amazon.com/s3/)
[![AWS](https://img.shields.io/badge/AWS-Cloud-FF9900.svg?style=flat&logo=amazon-aws&logoColor=white)](https://aws.amazon.com)

Microservice d'agrégation vidéo qui **combine vidéos compressées et sous-titres générés** pour produire une vidéo finale avec sous-titres incrustés (burned-in). Utilise **Amazon S3** pour le stockage et **Amazon DynamoDB** pour les métadonnées.

---

## 📋 Table des matières

- [Vue d'ensemble](#-vue-densemble)
- [Architecture](#-architecture)
- [Fonctionnalités](#-fonctionnalités)
- [Services AWS](#-services-aws)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Utilisation](#-utilisation)
- [API Endpoints](#-api-endpoints)
- [Déploiement AWS](#-déploiement-aws)
- [Streaming vidéo](#-streaming-vidéo)
- [Monitoring](#-monitoring)
- [Dépannage](#-dépannage)

---

## 🎯 Vue d'ensemble

### Rôle du microservice

Le **Video Aggregation Service** est le **microservice final** du pipeline de traitement vidéo VidP. Il :

1. **Reçoit** une vidéo uploadée
2. **Télécharge** les sous-titres SRT depuis le microservice de génération
3. **Incruste** les sous-titres dans la vidéo (burning) via FFmpeg
4. **Compresse** la vidéo selon la résolution cible
5. **Stocke** la vidéo finale sur **Amazon S3**
6. **Enregistre** les métadonnées dans **Amazon DynamoDB**
7. **Fournit** une URL presignée S3 pour le streaming

### Position dans l'architecture globale

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PIPELINE VIDP COMPLET                           │
└─────────────────────────────────────────────────────────────────────┘

   Client Upload
        │
        ├──> 1. vidp-main-app (Orchestrateur)
        │         └──> Extraction audio
        │
        ├──> 2. app_langscale (Détection langue)
        │         └──> API Google Speech
        │
        ├──> 3. app_subtitle (Génération sous-titres)
        │         └──> Whisper + SRT
        │
        ├──> 4. app_downscale (Compression vidéo)
        │         └──> FFmpeg compression
        │
        └──> 5. app_agregation ⭐ (CE SERVICE)
                  │
                  ├──> Reçoit vidéo + SRT
                  ├──> Incruste sous-titres (FFmpeg)
                  ├──> Upload vers Amazon S3
                  ├──> Sauvegarde métadonnées (DynamoDB)
                  └──> Fournit URL presignée S3
                        │
                        └──> Client streame la vidéo finale
```

---

## 🏗 Architecture

### Composants principaux

```
app_agregation/
├── main.py                      # Point d'entrée FastAPI
├── requirements.txt             # Dépendances Python
│
├── api/
│   └── routes.py               # Endpoints REST
│
├── config/
│   └── settings.py             # Configuration (Pydantic)
│
├── models/
│   └── video.py                # Modèles Pydantic (vidéo)
│
├── services/
│   ├── ffmpeg_service.py       # Service de traitement FFmpeg
│   ├── s3_service.py           # Service Amazon S3
│   └── dynamodb_service.py     # Service Amazon DynamoDB
│
├── utils/
│   ├── exceptions.py           # Gestion d'erreurs
│   ├── file_utils.py           # Utilitaires fichiers
│   └── logging_config.py       # Configuration logs
│
└── video_storage/              # Stockage permanent (S3 sur AWS)
    └── <job_id>_final.mp4
```

### Technologies utilisées

- **FastAPI** - Framework web asynchrone haute performance
- **FFmpeg** - Traitement vidéo (burning de sous-titres, compression)
- **Amazon S3** - Stockage permanent des vidéos
- **Amazon DynamoDB** - Stockage des métadonnées vidéo
- **Uvicorn** - Serveur ASGI
- **Pydantic** - Validation des données
- **HTTPX** - Client HTTP asynchrone (téléchargement SRT)
- **AWS ECS/EKS** - Orchestration des conteneurs
- **AWS CloudWatch** - Monitoring et logs

---

## ✨ Fonctionnalités

### Fonctionnalités principales

- 🎥 **Agrégation vidéo/sous-titres** : Combine vidéo et SRT en une vidéo finale
- 🔥 **Burning de sous-titres** : Incruste les sous-titres directement dans la vidéo
- 📦 **Compression vidéo** : Réduit la taille selon la résolution cible (360p à 1080p)
- 💾 **Stockage S3** : Sauvegarde sur Amazon S3
- 📊 **Métadonnées DynamoDB** : Enregistre durée, taille, résolution, statut
- 📡 **Streaming HTTP** : Fournit des URLs presignées pour lecture directe
- 🔄 **Traitement asynchrone** : Traite les vidéos en arrière-plan
- 🧹 **Nettoyage automatique** : Supprime les fichiers temporaires

### Formats supportés

**Entrée** :
- Vidéo : `.mp4`, `.avi`, `.mov`, `.mkv`
- Sous-titres : SRT (via URL du microservice `app_subtitle`)

**Sortie** :
- Vidéo finale : `.mp4` (H.264 + AAC)

### Résolutions supportées

| Résolution | Dimensions | Usage typique |
|------------|-----------|---------------|
| **360p** | 640×360 | Mobile, bande passante limitée |
| **480p** | 854×480 | Qualité standard |
| **720p** | 1280×720 | HD, usage général |
| **1080p** | 1920×1080 | Full HD, haute qualité |

---

## 🛠 Services AWS

### Amazon S3 (Simple Storage Service)

- **Stockage des vidéos** : Les vidéos traitées sont stockées dans un bucket S3
- **URLs Presignées** : Génération d'URLs temporaires sécurisées pour le streaming
- **Streaming natif** : Support des requêtes Range pour le streaming vidéo

### Amazon DynamoDB

- **Base de données NoSQL** : Stockage des métadonnées vidéo
- **Indexes secondaires globaux (GSI)** :
  - `status-created_at-index` : Recherche par statut
  - `source_video_id-index` : Liaison avec le service principal
  - `filename-index` : Recherche par nom de fichier
- **Scalabilité automatique** : Pas de gestion de serveur

---

## 📦 Prérequis

### Système

- **Python** 3.8 ou supérieur
- **FFmpeg** 4.0+ - [Télécharger FFmpeg](https://www.ffmpeg.org/download.html)
- **AWS CLI** configuré avec les credentials

### Installation de FFmpeg

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

#### macOS
```bash
brew install ffmpeg
```

#### Windows
1. Téléchargez depuis [ffmpeg.org](https://www.ffmpeg.org/download.html)
2. Ajoutez `ffmpeg.exe` au PATH système

**Vérification** :
```bash
ffmpeg -version
```

### Services externes requis

- **app_subtitle** : Microservice de génération de sous-titres
- **Amazon S3** : Stockage des vidéos
- **Amazon DynamoDB** : Base de données pour les métadonnées

---

## 🚀 Installation

### 1. Cloner le projet

```bash
cd vidp-app/app_agregation
```

### 2. Créer un environnement virtuel

```bash
# Créer l'environnement
python -m venv venv

# Activer l'environnement
# Linux/macOS :
source venv/bin/activate
# Windows :
venv\Scripts\activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

```bash
# Copier le fichier d'exemple
cp .env.example .env

# Éditer les variables
nano .env
```

### 5. Créer les répertoires de stockage

```bash
mkdir -p video_storage
mkdir -p temp
```

---

## ⚙️ Configuration

### Variables d'environnement

Créez un fichier `.env` à la racine du projet :

```bash
# ============================================================================
# Server Configuration
# ============================================================================
HOST=0.0.0.0
PORT=8000
DEBUG=False
WORKERS=1

# Public URL of this service (for generating streaming links)
API_URL=http://localhost:8000

# ============================================================================
# Amazon S3 Configuration
# ============================================================================
AWS_REGION=us-east-1
AWS_S3_BUCKET=vidp-video-storage
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_PRESIGNED_URL_EXPIRATION=3600

# ============================================================================
# Amazon DynamoDB Configuration
# ============================================================================
DYNAMODB_TABLE_NAME=vidp_videos

# ============================================================================
# Timeout Configuration (seconds)
# ============================================================================
HTTP_TIMEOUT=600.0
SUBTITLE_TIMEOUT=600.0
COMPRESSION_TIMEOUT=600.0

# ============================================================================
# Storage Configuration
# ============================================================================
# Taille maximale d'upload (500MB par défaut)
MAX_UPLOAD_SIZE=524288000

# Répertoire de stockage permanent des vidéos
# VIDEO_STORAGE_DIR=/var/video_storage

# Répertoire temporaire
# TEMP_DIR=/tmp/aggregator_service

# ============================================================================
# Video Streaming Configuration
# ============================================================================
# Taille des chunks pour le streaming (1MB)
CHUNK_SIZE=1048576

# ============================================================================
# FFmpeg Configuration
# ============================================================================
FFMPEG_PRESET=medium
FFMPEG_CODEC=libx264
FFMPEG_TIMEOUT=600

# ============================================================================
# Logging Configuration
# ============================================================================
LOG_LEVEL=INFO
# Laisser vide pour logs vers stdout/stderr uniquement
# LOG_FILE=app.log

# ============================================================================
# Security Configuration
# ============================================================================
ALLOWED_EXTENSIONS=[".mp4", ".avi", ".mov", ".mkv"]
```

### Configuration AWS (Production)

Pour un déploiement sur AWS, ajoutez :

```bash
# AWS S3 Configuration
AWS_REGION=us-east-1
AWS_S3_BUCKET=vidp-video-storage
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# Utiliser S3 au lieu du système de fichiers local
USE_S3_STORAGE=true

# AWS DynamoDB Configuration
DYNAMODB_TABLE_NAME=vidp_videos

# CloudWatch Logs
AWS_CLOUDWATCH_LOG_GROUP=/aws/ecs/vidp-aggregation
```

---

## 🎯 Utilisation

### Démarrage en développement

```bash
# Méthode 1 : Via uvicorn directement
uvicorn main:app --reload --port 8000

# Méthode 2 : Via le script Python
python main.py
```

Le service sera accessible sur `http://localhost:8000`

### Documentation interactive

- **Swagger UI** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc
- **Health Check** : http://localhost:8000/api/health

---

## 🔌 API Endpoints

### 1. Traiter une vidéo avec sous-titres

**POST** `/api/process-video/`

Agrège une vidéo avec des sous-titres SRT et produit une vidéo finale.

**Form Data** :
- `video` (file) : Fichier vidéo à traiter (requis)
- `srt_file` (file) : Fichier SRT contenant les sous-titres (requis)
- `resolution` (string) : Résolution cible - `360p`, `480p`, `720p`, `1080p` (défaut: `360p`)
- `crf_value` (int) : Qualité vidéo CRF 0-51, plus bas = meilleure qualité (défaut: `23`)

**Exemple avec cURL** :
```bash
curl -X POST "http://localhost:8005/api/process-video/" \
  -F "video=@my_video.mp4" \
  -F "srt_file=@subtitles.srt" \
  -F "resolution=720p" \
  -F "crf_value=23"
```

**Réponse (succès)** :
```json
{
  "status": "success",
  "video_id": "65f1234567890abcdef12345",
  "job_id": "job_a1b2c3d4",
  "message": "Video processed and stored successfully",
  "streaming_url": "https://vidp-video-storage.s3.amazonaws.com/job_a1b2c3d4_final.mp4?...",
  "metadata": {
    "original_filename": "my_video.mp4",
    "final_filename": "job_a1b2c3d4_final.mp4",
    "resolution": "1280x720",
    "duration": 125.5,
    "file_size": 15728640
  }
}
```

---

### 2. Récupérer une vidéo par ID

**GET** `/api/videos/{video_id}`

Récupère les métadonnées d'une vidéo.

**Exemple** :
```bash
curl http://localhost:8000/api/videos/65f1234567890abcdef12345
```

**Réponse** :
```json
{
  "id": "65f1234567890abcdef12345",
  "filename": "my_video.mp4",
  "s3_uri": "s3://vidp-video-storage/job_a1b2c3d4_final.mp4",
  "link": "https://vidp-video-storage.s3.amazonaws.com/job_a1b2c3d4_final.mp4?...",
  "status": "saved",
  "file_size": 15728640,
  "duration": 125.5,
  "resolution": "1280x720",
  "created_at": "2026-01-14T10:30:00Z",
  "updated_at": "2026-01-14T10:32:15Z"
}
```

---

### 3. Lister toutes les vidéos

**GET** `/api/videos/`

Liste toutes les vidéos avec pagination.

**Query Parameters** :
- `skip` (int) : Nombre d'éléments à sauter (défaut: `0`)
- `limit` (int) : Nombre maximum d'éléments (défaut: `50`)
- `status` (string) : Filtrer par statut - `processing`, `saved`, `failed`

**Exemple** :
```bash
curl "http://localhost:8000/api/videos/?limit=10&status=saved"
```

---

### 4. Streamer une vidéo

**GET** `/api/stream/{video_id}`

Stream une vidéo avec support du Range HTTP (lecture progressive).

**Exemple** :
```bash
# Dans un navigateur
http://localhost:8000/api/stream/65f1234567890abcdef12345

# Avec curl (téléchargement)
curl -o video.mp4 "http://localhost:8000/api/stream/65f1234567890abcdef12345"
```

**Headers supportés** :
- `Range: bytes=0-1023` : Lecture partielle (streaming progressif)

---

### 5. Mettre à jour le statut d'une vidéo

**PATCH** `/api/videos/{video_id}`

Met à jour les métadonnées d'une vidéo.

**Body** :
```json
{
  "status": "saved",
  "file_size": 15728640,
  "duration": 125.5,
  "resolution": "1280x720"
}
```

---

### 6. Supprimer une vidéo

**DELETE** `/api/videos/{video_id}`

Supprime une vidéo et ses métadonnées.

**Exemple** :
```bash
curl -X DELETE "http://localhost:8000/api/videos/65f1234567890abcdef12345"
```

---

### 7. Santé du service

**GET** `/api/health`

Vérifie l'état de santé du service.

**Réponse** :
```json
{
  "status": "healthy",
  "service": "Video Aggregation Service",
  "version": "2.0.0",
  "s3": "connected",
  "dynamodb": "connected",
  "ffmpeg": "available"
}
```

---

## ☁️ Déploiement AWS

### Architecture AWS recommandée

```
┌────────────────────────────────────────────────────────────────┐
│                         AWS CLOUD                              │
└────────────────────────────────────────────────────────────────┘

Internet Gateway
      │
      ├──> Application Load Balancer (ALB)
      │         │
      │         ├──> Target Group: app_agregation
      │         │         │
      │         │         └──> ECS Service (Fargate)
      │         │                   │
      │         │                   ├──> Task 1 (Container)
      │         │                   ├──> Task 2 (Container)
      │         │                   └──> Task N (auto-scaling)
      │         │
      │         └──> Target Group: app_subtitle
      │
      ├──> Amazon S3 (vidp-video-storage)
      │         │
      │         ├──> /videos/
      │         └──> /temp/
      │
      ├──> Amazon DynamoDB
      │         └──> Table: vidp_videos
      │
      ├──> Amazon CloudWatch
      │         ├──> Logs
      │         ├──> Metrics
      │         └──> Alarms
      │
      └──> AWS Secrets Manager
                └──> MongoDB credentials
                └──> S3 access keys
```

### 1. Préparation de l'image Docker

**Créez un `Dockerfile`** :

```dockerfile
FROM python:3.10-slim

# Installer FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Définir le répertoire de travail
WORKDIR /app

# Copier les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY . .

# Créer les répertoires de stockage
RUN mkdir -p /app/video_storage /app/temp

# Exposer le port
EXPOSE 8000

# Santé du conteneur
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/api/health')"

# Lancer l'application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2. Build et push vers ECR

```bash
# Authentification ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build de l'image
docker build -t vidp-aggregation:latest .

# Tag de l'image
docker tag vidp-aggregation:latest \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/vidp-aggregation:latest

# Push vers ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/vidp-aggregation:latest
```

### 3. Déploiement sur ECS Fargate

**Créez une Task Definition** (`ecs-task-definition.json`) :

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
        {"name": "AWS_REGION", "value": "us-east-1"}
      ],
      "secrets": [
        {
          "name": "DYNAMODB_TABLE_NAME",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:<account-id>:secret:vidp/dynamodb-table-name"
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

**Déployez la task** :

```bash
# Créer la task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json

# Créer le service ECS
aws ecs create-service \
  --cluster vidp-cluster \
  --service-name aggregation-service \
  --task-definition vidp-aggregation \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-zzz],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=aggregation-container,containerPort=8000"
```

### 4. Configuration du S3 Bucket

```bash
# Créer le bucket
aws s3 mb s3://vidp-video-storage --region us-east-1

# Configurer les permissions (pour l'IAM role ECS)
aws s3api put-bucket-policy --bucket vidp-video-storage --policy file://s3-bucket-policy.json

# Activer le versioning (optionnel)
aws s3api put-bucket-versioning --bucket vidp-video-storage --versioning-configuration Status=Enabled

# Configurer la lifecycle policy (suppression automatique après 30 jours)
aws s3api put-bucket-lifecycle-configuration \
  --bucket vidp-video-storage \
  --lifecycle-configuration file://s3-lifecycle-policy.json
```

**Exemple de lifecycle policy** (`s3-lifecycle-policy.json`) :
```json
{
  "Rules": [
    {
      "Id": "Delete temp files after 1 day",
      "Filter": {"Prefix": "temp/"},
      "Status": "Enabled",
      "Expiration": {"Days": 1}
    },
    {
      "Id": "Archive old videos after 90 days",
      "Filter": {"Prefix": "videos/"},
      "Status": "Enabled",
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

### 5. Configuration de l'ALB

```bash
# Créer un target group
aws elbv2 create-target-group \
  --name vidp-aggregation-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id vpc-xxx \
  --target-type ip \
  --health-check-path /api/health \
  --health-check-interval-seconds 30

# Ajouter une règle de listener
aws elbv2 create-rule \
  --listener-arn arn:aws:elasticloadbalancing:... \
  --priority 100 \
  --conditions Field=path-pattern,Values='/api/process-video/*' \
  --actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...
```

### 6. Auto-scaling

```bash
# Créer une scaling policy
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/vidp-cluster/aggregation-service \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# Créer une politique de scaling basée sur le CPU
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/vidp-cluster/aggregation-service \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-scaling-policy \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

---

## 📡 Streaming vidéo

### Support du protocole HTTP Range

Le service supporte le **Range HTTP** pour le streaming progressif :

```http
GET /api/stream/65f1234567890abcdef12345 HTTP/1.1
Range: bytes=0-1048575

HTTP/1.1 206 Partial Content
Content-Range: bytes 0-1048575/15728640
Content-Length: 1048576
Content-Type: video/mp4
```

### Intégration avec un player HTML5

```html
<video controls width="800">
  <source src="https://vidp-video-storage.s3.amazonaws.com/job_a1b2c3d4_final.mp4?..." type="video/mp4">
  Your browser does not support the video tag.
</video>
```

### Intégration avec AWS CloudFront (CDN)

Pour améliorer les performances en production, utilisez CloudFront :

1. **Créer une distribution CloudFront** pointant vers l'ALB
2. **Configurer le cache** avec une TTL appropriée
3. **Activer la compression** (Gzip/Brotli)
4. **Utiliser CloudFront** comme URL de base dans `API_URL`

```bash
# Exemple d'URL avec CloudFront
API_URL=https://d1234567890.cloudfront.net
```

---

## 📊 Monitoring

### CloudWatch Metrics

Métriques clés à surveiller :

- **CPU Utilization** : % d'utilisation CPU (ECS)
- **Memory Utilization** : % d'utilisation mémoire (ECS)
- **Request Count** : Nombre de requêtes par minute
- **Request Duration** : Temps de traitement moyen
- **Error Rate** : Taux d'erreur 4xx/5xx
- **Storage Usage** : Utilisation du S3 bucket

### CloudWatch Logs

Les logs sont envoyés vers CloudWatch Logs :

```bash
# Consulter les logs en temps réel
aws logs tail /ecs/vidp-aggregation --follow

# Rechercher des erreurs
aws logs filter-log-events \
  --log-group-name /ecs/vidp-aggregation \
  --filter-pattern "ERROR"
```

### Alarmes CloudWatch

```bash
# Alarme CPU élevé
aws cloudwatch put-metric-alarm \
  --alarm-name vidp-aggregation-high-cpu \
  --alarm-description "Alerte si CPU > 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2

# Alarme taux d'erreur
aws cloudwatch put-metric-alarm \
  --alarm-name vidp-aggregation-high-error-rate \
  --alarm-description "Alerte si taux d'erreur > 5%" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 60 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 3
```

---

## 🔧 Dépannage

### Problème : FFmpeg non trouvé

**Erreur** : `FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'`

**Solution** :
```bash
# Vérifier l'installation
ffmpeg -version

# Sur Docker, vérifier le Dockerfile
RUN apt-get install -y ffmpeg
```

---

### Problème : Fichier SRT vide ou invalide

**Erreur** : `SRT file is empty`

**Solutions** :
1. Vérifier que le fichier SRT n'est pas vide
2. Vérifier le format du fichier SRT
3. S'assurer que le fichier est bien encodé en UTF-8

```bash
# Vérifier le contenu du fichier SRT
cat subtitles.srt
head -n 10 subtitles.srt

# Vérifier l'encodage
file subtitles.srt
```

---

### Problème : S3 permissions denied

**Erreur** : `AccessDenied: Access Denied`

**Solution** : Vérifier l'IAM role ECS :

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
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
    }
  ]
}
```

---

## 📚 Documentation API complète

### Accès à la documentation

- **Swagger UI** : `http://<host>:<port>/docs`
- **ReDoc** : `http://<host>:<port>/redoc`
- **OpenAPI JSON** : `http://<host>:<port>/openapi.json`

### Exemples d'intégration

#### Python

```python
import requests

# Traiter une vidéo avec fichier SRT
with open("video.mp4", "rb") as video_file, open("subtitles.srt", "rb") as srt_file:
    response = requests.post(
        "http://localhost:8005/api/process-video/",
        files={
            "video": video_file,
            "srt_file": srt_file
        },
        data={
            "resolution": "720p",
            "crf_value": 23
        }
    )
    result = response.json()
    print(f"Streaming URL: {result['streaming_url']}")
```

#### JavaScript/Node.js

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

async function processVideo() {
  const form = new FormData();
  form.append('video', fs.createReadStream('video.mp4'));
  form.append('srt_file', fs.createReadStream('subtitles.srt'));
  form.append('resolution', '720p');
  form.append('crf_value', '23');
  
  const response = await axios.post(
    'http://localhost:8005/api/process-video/',
    form,
    {headers: form.getHeaders()}
  );
  
  console.log('Streaming URL:', response.data.streaming_url);
}
```

---

## 🔐 Sécurité

### Bonnes pratiques

1. **Secrets** : Utilisez AWS Secrets Manager pour les credentials
2. **IAM Roles** : Utilisez des IAM roles au lieu de clés d'accès
3. **Network** : Utilisez des security groups restrictifs
4. **Encryption** : Activez le chiffrement S3 (SSE-S3 ou SSE-KMS)
5. **HTTPS** : Utilisez HTTPS avec un certificat SSL (ACM)
6. **CORS** : Configurez CORS de manière restrictive en production
7. **Rate Limiting** : Implémentez un rate limiting (API Gateway ou ALB)

---

## 📞 Support et Contributions

### Bugs et Questions

Pour signaler un bug ou poser une question :
1. Vérifiez les logs CloudWatch
2. Consultez cette documentation
3. Créez une issue sur le repository

### Logs

```bash
# Niveau DEBUG pour plus de détails
LOG_LEVEL=DEBUG

# Consulter les logs
# Local
docker logs -f <container-id>

# AWS
aws logs tail /ecs/vidp-aggregation --follow
```

---

## 📝 Changelog

### Version 2.0.0 (2026-01-14)
- ✅ Refactoring complet de l'architecture
- ✅ Support AWS S3 pour le stockage
- ✅ Support AWS DynamoDB pour les métadonnées
- ✅ Streaming HTTP avec Range support
- ✅ Amélioration de la gestion d'erreurs
- ✅ Logs structurés vers stdout/stderr
- ✅ Documentation complète

### Version 1.0.0 (Initial)
- ✅ Agrégation vidéo/sous-titres
- ✅ Burning de sous-titres FFmpeg
- ✅ Stockage MongoDB
- ✅ API REST de base

---

## 📄 Licence

Ce projet est développé dans le cadre du projet VidP - Master 2 DS - INF5141 Cloud Computing.

---

**Service d'agrégation vidéo prêt pour le Cloud AWS !** ☁️🎬
