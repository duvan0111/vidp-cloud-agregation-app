# 🚀 Guide Complet de Déploiement EC2 avec CI/CD

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture EC2](#architecture-ec2)
3. [Prérequis](#prérequis)
4. [Étape 1 : Configuration AWS](#étape-1--configuration-aws)
5. [Étape 2 : Lancement de l'Instance EC2](#étape-2--lancement-de-linstance-ec2)
6. [Étape 3 : Installation et Configuration](#étape-3--installation-et-configuration)
7. [Étape 4 : Déploiement de l'Application](#étape-4--déploiement-de-lapplication)
8. [Étape 5 : Configuration Systemd](#étape-5--configuration-systemd)
9. [Étape 6 : Configuration Nginx (Reverse Proxy)](#étape-6--configuration-nginx-reverse-proxy)
10. [Étape 7 : CI/CD avec GitHub Actions](#étape-7--cicd-avec-github-actions)
11. [Monitoring et Logs](#monitoring-et-logs)
12. [Sécurité et Bonnes Pratiques](#sécurité-et-bonnes-pratiques)
13. [Maintenance et Mises à Jour](#maintenance-et-mises-à-jour)
14. [Troubleshooting](#troubleshooting)

---

## 🎯 Vue d'ensemble

Ce guide vous accompagne dans le déploiement du **Video Aggregation Service** sur une instance **Amazon EC2** avec un pipeline **CI/CD complet** utilisant **GitHub Actions**.

### Architecture Déployée

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTERNET                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Route 53 (DNS)  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Elastic IP     │
                    └────────┬────────┘
                             │
        ┌────────────────────▼────────────────────┐
        │         AWS EC2 Instance                │
        │  ┌──────────────────────────────────┐   │
        │  │   Nginx (Reverse Proxy)          │   │
        │  │   Port 80/443 → 8005             │   │
        │  └────────────┬─────────────────────┘   │
        │               │                          │
        │  ┌────────────▼─────────────────────┐   │
        │  │  Video Aggregation Service       │   │
        │  │  (Systemd Service)               │   │
        │  │  Port: 8005                      │   │
        │  └────────────┬─────────────────────┘   │
        │               │                          │
        │  ┌────────────▼─────────────────────┐   │
        │  │  FFmpeg (Video Processing)       │   │
        │  └──────────────────────────────────┘   │
        └─────────────────────────────────────────┘
                      │          │
         ┌────────────┘          └────────────┐
         │                                     │
┌────────▼────────┐                  ┌────────▼────────┐
│   Amazon S3     │                  │  Amazon DynamoDB│
│  (Video Storage)│                  │   (Metadata)    │
└─────────────────┘                  └─────────────────┘
         ▲
         │
┌────────┴────────┐
│  GitHub Actions │
│    (CI/CD)      │
└─────────────────┘
```

### Flux de Déploiement CI/CD

```
Developer Push → GitHub → GitHub Actions → SSH to EC2 → Deploy
                                              ↓
                                        Run Tests
                                              ↓
                                     Restart Service
                                              ↓
                                    Health Check
```

---

## 📦 Prérequis

### Sur votre machine locale

```bash
# AWS CLI
aws --version  # >= 2.0

# SSH Client
ssh -V

# Git
git --version
```

### Comptes et Accès

- ✅ Compte AWS avec accès administrateur
- ✅ Compte GitHub avec accès au repository
- ✅ Paire de clés SSH générée

### Services AWS Requis

- ✅ Amazon S3 Bucket créé
- ✅ Amazon DynamoDB Table créée
- ✅ IAM User/Role avec permissions appropriées

---

## 🔐 Étape 1 : Configuration AWS

### 1.1 Créer un IAM User pour EC2

```bash
# Créer un utilisateur IAM
aws iam create-user --user-name vidp-ec2-user

# Créer une politique pour S3 et DynamoDB
cat > ec2-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3FullAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::mon-bucket-vidp",
        "arn:aws:s3:::mon-bucket-vidp/*"
      ]
    },
    {
      "Sid": "DynamoDBFullAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/vidp-metadata"
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
    }
  ]
}
EOF

# Créer la politique
aws iam create-policy \
  --policy-name VidpEC2Policy \
  --policy-document file://ec2-policy.json

# Attacher la politique à l'utilisateur
aws iam attach-user-policy \
  --user-name vidp-ec2-user \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/VidpEC2Policy

# Créer des access keys
aws iam create-access-key --user-name vidp-ec2-user
```

Notez les valeurs de `AccessKeyId` et `SecretAccessKey` retournées.

### 1.2 Créer un S3 Bucket

```bash
# Créer le bucket
aws s3 mb s3://mon-bucket-vidp --region us-east-1

# Configurer CORS pour le bucket
cat > cors-config.json << 'EOF'
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
EOF

aws s3api put-bucket-cors \
  --bucket mon-bucket-vidp \
  --cors-configuration file://cors-config.json

# Configurer lifecycle (optionnel - suppression auto après 90 jours)
cat > lifecycle-config.json << 'EOF'
{
  "Rules": [
    {
      "Id": "DeleteOldVideos",
      "Status": "Enabled",
      "Prefix": "",
      "Expiration": {
        "Days": 90
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket mon-bucket-vidp \
  --lifecycle-configuration file://lifecycle-config.json
```

### 1.3 Créer une Table DynamoDB

```bash
# Créer la table
aws dynamodb create-table \
  --table-name vidp-metadata \
  --attribute-definitions \
    AttributeName=id,AttributeType=S \
    AttributeName=status,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
  --key-schema \
    AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
    '[
      {
        "IndexName": "status-created_at-index",
        "KeySchema": [
          {"AttributeName": "status", "KeyType": "HASH"},
          {"AttributeName": "created_at", "KeyType": "RANGE"}
        ],
        "Projection": {"ProjectionType": "ALL"}
      }
    ]' \
  --region us-east-1

# Vérifier la création
aws dynamodb describe-table --table-name vidp-metadata
```

---

## 🖥️ Étape 2 : Lancement de l'Instance EC2

### 2.1 Créer une Paire de Clés SSH

```bash
# Créer une paire de clés
aws ec2 create-key-pair \
  --key-name vidp-ec2-key \
  --query 'KeyMaterial' \
  --output text > vidp-ec2-key.pem

# Sécuriser la clé
chmod 400 vidp-ec2-key.pem
```

### 2.2 Créer un Security Group

```bash
# Créer le security group
aws ec2 create-security-group \
  --group-name vidp-security-group \
  --description "Security group for VIDP Video Aggregation Service" \
  --vpc-id vpc-YOUR_VPC_ID

# Récupérer l'ID du security group
SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values=vidp-security-group \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

echo "Security Group ID: $SG_ID"

# Autoriser SSH (port 22)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0

# Autoriser HTTP (port 80)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

# Autoriser HTTPS (port 443)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

# Autoriser l'application (port 8005 - optionnel, pour debug)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 8005 \
  --cidr 0.0.0.0/0
```

### 2.3 Lancer l'Instance EC2

```bash
# Lancer l'instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name vidp-ec2-key \
  --security-group-ids $SG_ID \
  --block-device-mappings '[
    {
      "DeviceName": "/dev/sda1",
      "Ebs": {
        "VolumeSize": 30,
        "VolumeType": "gp3",
        "DeleteOnTermination": true
      }
    }
  ]' \
  --tag-specifications \
    'ResourceType=instance,Tags=[
      {Key=Name,Value=vidp-aggregation-server},
      {Key=Project,Value=VIDP},
      {Key=Environment,Value=production}
    ]' \
  --user-data file://user-data.sh

# Récupérer l'ID de l'instance
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=vidp-aggregation-server" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

echo "Instance ID: $INSTANCE_ID"

# Attendre que l'instance soit prête
aws ec2 wait instance-running --instance-ids $INSTANCE_ID

# Récupérer l'IP publique
PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo "Public IP: $PUBLIC_IP"
```

### 2.4 Créer un Script User Data (optionnel)

Créez `user-data.sh` pour l'initialisation automatique :

```bash
#!/bin/bash
# user-data.sh - Script d'initialisation EC2

# Mettre à jour le système
apt-get update -y
apt-get upgrade -y

# Installer les outils de base
apt-get install -y \
  git \
  curl \
  wget \
  htop \
  vim

# Installer FFmpeg
apt-get install -y ffmpeg

# Créer l'utilisateur de déploiement
useradd -m -s /bin/bash deploy
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh

# Configurer sudo sans mot de passe
echo "deploy ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/deploy

echo "EC2 initialization complete"
```

### 2.5 Allouer une Elastic IP (Recommandé)

```bash
# Allouer une Elastic IP
ALLOCATION_ID=$(aws ec2 allocate-address \
  --domain vpc \
  --query 'AllocationId' \
  --output text)

echo "Elastic IP Allocation ID: $ALLOCATION_ID"

# Associer l'Elastic IP à l'instance
aws ec2 associate-address \
  --instance-id $INSTANCE_ID \
  --allocation-id $ALLOCATION_ID

# Récupérer l'Elastic IP
ELASTIC_IP=$(aws ec2 describe-addresses \
  --allocation-ids $ALLOCATION_ID \
  --query 'Addresses[0].PublicIp' \
  --output text)

echo "Elastic IP: $ELASTIC_IP"
echo "Connectez-vous avec: ssh -i vidp-ec2-key.pem ubuntu@$ELASTIC_IP"
```

---

## 🔧 Étape 3 : Installation et Configuration

### 3.1 Connexion à l'Instance

```bash
# Se connecter via SSH
ssh -i vidp-ec2-key.pem ubuntu@$ELASTIC_IP

# Ou si vous utilisez l'IP publique
ssh -i vidp-ec2-key.pem ubuntu@$PUBLIC_IP
```

### 3.2 Installation Automatique via Script

Uploadez et exécutez le script de déploiement :

```bash
# Sur votre machine locale
scp -i vidp-ec2-key.pem deploy_ec2.sh ubuntu@$ELASTIC_IP:~/
scp -i vidp-ec2-key.pem install_ffmpeg.sh ubuntu@$ELASTIC_IP:~/

# Sur l'instance EC2
ssh -i vidp-ec2-key.pem ubuntu@$ELASTIC_IP

# Exécuter le script
chmod +x deploy_ec2.sh
./deploy_ec2.sh
```

### 3.3 Installation Manuelle (Alternative)

Si vous préférez installer manuellement :

```bash
# Sur l'instance EC2

# 1. Mettre à jour le système
sudo apt-get update -y
sudo apt-get upgrade -y

# 2. Installer FFmpeg (CRITIQUE)
sudo apt-get install -y ffmpeg libmagic1

# Vérifier FFmpeg
ffmpeg -version

# 3. Installer Python 3.10+
sudo apt-get install -y \
  python3.10 \
  python3.10-venv \
  python3-pip \
  python3.10-dev

# 4. Installer Nginx
sudo apt-get install -y nginx

# 5. Installer d'autres outils
sudo apt-get install -y \
  git \
  curl \
  wget \
  htop \
  vim \
  supervisor
```

### 3.4 Configurer AWS CLI sur EC2

```bash
# Installer AWS CLI
sudo apt-get install -y awscli

# Configurer les credentials
mkdir -p ~/.aws

cat > ~/.aws/credentials << EOF
[default]
aws_access_key_id = YOUR_ACCESS_KEY_ID
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
EOF

cat > ~/.aws/config << EOF
[default]
region = us-east-1
output = json
EOF

# Sécuriser les fichiers
chmod 600 ~/.aws/credentials
chmod 600 ~/.aws/config

# Tester la configuration
aws s3 ls s3://mon-bucket-vidp
aws dynamodb describe-table --table-name vidp-metadata
```

---

## 📂 Étape 4 : Déploiement de l'Application

### 4.1 Cloner le Repository

```bash
# Créer le répertoire de l'application
sudo mkdir -p /opt/vidp-aggregation
sudo chown ubuntu:ubuntu /opt/vidp-aggregation

# Cloner le repository
cd /opt/vidp-aggregation
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git .

# Ou si vous utilisez un repository privé
git clone https://YOUR_GITHUB_TOKEN@github.com/YOUR_USERNAME/YOUR_REPO.git .
```

### 4.2 Créer l'Environnement Virtuel

```bash
cd /opt/vidp-aggregation

# Créer l'environnement virtuel
python3.10 -m venv venv

# Activer l'environnement
source venv/bin/activate

# Mettre à jour pip
pip install --upgrade pip

# Installer les dépendances
pip install -r requirements.txt

# Vérifier l'installation
python check_dependencies.py
```

### 4.3 Configurer les Variables d'Environnement

```bash
# Créer le fichier .env
cat > /opt/vidp-aggregation/.env << 'EOF'
# AWS Configuration
AWS_REGION=us-east-1
S3_BUCKET_NAME=mon-bucket-vidp
DYNAMODB_TABLE_NAME=vidp-metadata

# Server Configuration
HOST=0.0.0.0
PORT=8005
DEBUG=false
WORKERS=2

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s

# FFmpeg Configuration
FFMPEG_PRESET=medium
FFMPEG_CODEC=libx264
FFMPEG_CRF=23
FFMPEG_TIMEOUT=600

# API Configuration
API_TITLE=Video Aggregation Service
API_VERSION=2.0.0
API_DESCRIPTION=Microservice for video aggregation and subtitle burning
EOF

# Sécuriser le fichier
chmod 600 /opt/vidp-aggregation/.env
```

### 4.4 Créer les Répertoires Nécessaires

```bash
# Créer les répertoires
sudo mkdir -p /opt/vidp-aggregation/temp_aggregator
sudo mkdir -p /opt/vidp-aggregation/video_storage
sudo mkdir -p /var/log/vidp-aggregation

# Définir les permissions
sudo chown -R ubuntu:ubuntu /opt/vidp-aggregation
sudo chown -R ubuntu:ubuntu /var/log/vidp-aggregation
```

---

## ⚙️ Étape 5 : Configuration Systemd

### 5.1 Créer le Service Systemd

```bash
# Créer le fichier service
sudo tee /etc/systemd/system/vidp-aggregation.service > /dev/null << 'EOF'
[Unit]
Description=Video Aggregation Service
After=network.target
Documentation=https://github.com/duvan0111/vidp-cloud-agregation-app.git

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/aggregation
# Environment="PATH=/opt/vidp-aggregation/venv/bin"
EnvironmentFile=/home/ubuntu/aggregation/.env

# Commande de démarrage
ExecStart=/home/ubuntu/aggregation/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8005 --workers 2

# Restart automatique
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Limites de ressources
LimitNOFILE=65536
LimitNPROC=4096

# Sécurité
NoNewPrivileges=true
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vidp-aggregation

[Install]
WantedBy=multi-user.target
EOF
```

### 5.2 Activer et Démarrer le Service

```bash
# Recharger systemd
sudo systemctl daemon-reload

# Activer le service au démarrage
sudo systemctl enable vidp-aggregation

# Démarrer le service
sudo systemctl start vidp-aggregation

# Vérifier le statut
sudo systemctl status vidp-aggregation

# Voir les logs en temps réel
sudo journalctl -u vidp-aggregation -f
```

### 5.3 Commandes Utiles

```bash
# Démarrer
sudo systemctl start vidp-aggregation

# Arrêter
sudo systemctl stop vidp-aggregation

# Redémarrer
sudo systemctl restart vidp-aggregation

# Recharger la configuration
sudo systemctl reload vidp-aggregation

# Voir le statut
sudo systemctl status vidp-aggregation

# Voir les logs
sudo journalctl -u vidp-aggregation -n 100 --no-pager

# Suivre les logs en temps réel
sudo journalctl -u vidp-aggregation -f

# Voir les logs avec filtrage
sudo journalctl -u vidp-aggregation --since "1 hour ago"
sudo journalctl -u vidp-aggregation --grep ERROR
```

---

## 🌐 Étape 6 : Configuration Nginx (Reverse Proxy)

### 6.1 Installer et Configurer Nginx

```bash
# Installer Nginx (si pas déjà fait)
sudo apt-get install -y nginx

# Créer la configuration
sudo tee /etc/nginx/sites-available/vidp-aggregation > /dev/null << 'EOF'
# Upstream pour l'application
upstream vidp_app {
    server 127.0.0.1:8005 fail_timeout=0;
}

# Redirection HTTP vers HTTPS (après configuration SSL)
# server {
#     listen 80;
#     server_name your-domain.com;
#     return 301 https://$host$request_uri;
# }

# Configuration principale
server {
    listen 80;
    server_name your-domain.com;  # Remplacer par votre domaine ou IP
    
    # Taille maximale des uploads
    client_max_body_size 500M;
    client_body_timeout 600s;
    
    # Timeouts
    proxy_connect_timeout 600;
    proxy_send_timeout 600;
    proxy_read_timeout 600;
    send_timeout 600;
    
    # Logging
    access_log /var/log/nginx/vidp-aggregation-access.log;
    error_log /var/log/nginx/vidp-aggregation-error.log warn;
    
    # Root location
    location / {
        proxy_pass http://vidp_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (si nécessaire)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Buffers
        proxy_buffering off;
        proxy_request_buffering off;
    }
    
    # Health check endpoint
    location /api/health {
        proxy_pass http://vidp_app/api/health;
        access_log off;
    }
    
    # Static files (si nécessaire)
    location /static/ {
        alias /opt/vidp-aggregation/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Activer le site
sudo ln -sf /etc/nginx/sites-available/vidp-aggregation /etc/nginx/sites-enabled/

# Désactiver le site par défaut
sudo rm -f /etc/nginx/sites-enabled/default

# Tester la configuration
sudo nginx -t

# Redémarrer Nginx
sudo systemctl restart nginx

# Activer Nginx au démarrage
sudo systemctl enable nginx
```

### 6.2 Configuration SSL avec Let's Encrypt (Optionnel mais Recommandé)

```bash
# Installer Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Obtenir un certificat SSL
sudo certbot --nginx -d your-domain.com

# Le renouvellement automatique est configuré via cron
# Vérifier le renouvellement automatique
sudo certbot renew --dry-run

# Tester le site
curl https://your-domain.com/api/health
```

---

## 🔄 Étape 7 : CI/CD avec GitHub Actions

### 7.1 Configurer les Secrets GitHub

Dans votre repository GitHub, allez dans **Settings → Secrets and variables → Actions** et ajoutez :

| Secret Name | Description | Exemple |
|------------|-------------|---------|
| `EC2_HOST` | IP ou domaine EC2 | `54.123.45.67` |
| `EC2_USER` | Utilisateur SSH | `ubuntu` |
| `EC2_SSH_KEY` | Clé privée SSH | Contenu de `vidp-ec2-key.pem` |
| `AWS_ACCESS_KEY_ID` | AWS Access Key | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | AWS Secret Key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_REGION` | Région AWS | `us-east-1` |
| `S3_BUCKET_NAME` | Nom du bucket S3 | `mon-bucket-vidp` |
| `DYNAMODB_TABLE_NAME` | Nom de la table DynamoDB | `vidp-metadata` |

### 7.2 Créer le Workflow GitHub Actions

Créez `.github/workflows/deploy.yml` :

```yaml
name: Deploy to EC2

on:
  push:
    branches:
      - main
      - production
  workflow_dispatch:  # Permet le déclenchement manuel

env:
  APP_DIR: /home/ubuntu/aggregation

jobs:
  test:
    name: Run Tests
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      
      - name: Run tests
        run: |
          pytest tests/ -v --cov=. --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  deploy:
    name: Deploy to EC2
    runs-on: ubuntu-latest
    needs: test
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Configure SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.EC2_SSH_KEY }}" > ~/.ssh/id_rsa
          chmod 600 ~/.ssh/id_rsa
          ssh-keyscan -H ${{ secrets.EC2_HOST }} >> ~/.ssh/known_hosts
      
      - name: Create .env file
        run: |
          cat > .env << EOF
          AWS_REGION=${{ secrets.AWS_REGION }}
          S3_BUCKET_NAME=${{ secrets.S3_BUCKET_NAME }}
          DYNAMODB_TABLE_NAME=${{ secrets.DYNAMODB_TABLE_NAME }}
          HOST=0.0.0.0
          PORT=8005
          DEBUG=false
          WORKERS=2
          LOG_LEVEL=INFO
          FFMPEG_PRESET=medium
          FFMPEG_CODEC=libx264
          FFMPEG_CRF=23
          FFMPEG_TIMEOUT=600
          API_TITLE=Video Aggregation Service
          API_VERSION=2.0.0
          EOF
      
      - name: Deploy to EC2
        run: |
          ssh -o StrictHostKeyChecking=no ${{ secrets.EC2_USER }}@${{ secrets.EC2_HOST }} << 'ENDSSH'
            set -e
            
            echo "=========================================="
            echo "Starting deployment..."
            echo "=========================================="
            
            # Navigate to application directory
            cd ${{ env.APP_DIR }}
            
            # Pull latest code
            echo "Pulling latest code from GitHub..."
            git fetch origin
            git reset --hard origin/main
            
            # Activate virtual environment
            source venv/bin/activate
            
            # Install/update dependencies
            echo "Installing dependencies..."
            pip install --upgrade pip
            pip install -r requirements.txt
            
            # Run database migrations (si nécessaire)
            # python manage.py migrate
            
            # Restart the service
            echo "Restarting service..."
            sudo systemctl restart vidp-aggregation
            
            # Wait for service to start
            sleep 5
            
            # Check service status
            if sudo systemctl is-active --quiet vidp-aggregation; then
              echo "✅ Service started successfully"
            else
              echo "❌ Service failed to start"
              sudo journalctl -u vidp-aggregation -n 50 --no-pager
              exit 1
            fi
          ENDSSH
      
      - name: Upload .env to EC2
        run: |
          scp -o StrictHostKeyChecking=no .env \
            ${{ secrets.EC2_USER }}@${{ secrets.EC2_HOST }}:${{ env.APP_DIR }}/.env
      
      - name: Configure AWS credentials on EC2
        run: |
          ssh -o StrictHostKeyChecking=no ${{ secrets.EC2_USER }}@${{ secrets.EC2_HOST }} << 'ENDSSH'
            mkdir -p ~/.aws
            cat > ~/.aws/credentials << EOF
          [default]
          aws_access_key_id = ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws_secret_access_key = ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          EOF
            
            cat > ~/.aws/config << EOF
          [default]
          region = ${{ secrets.AWS_REGION }}
          output = json
          EOF
            
            chmod 600 ~/.aws/credentials
            chmod 600 ~/.aws/config
          ENDSSH
      
      - name: Health Check
        run: |
          echo "Waiting for service to be ready..."
          sleep 10
          
          MAX_RETRIES=5
          RETRY_COUNT=0
          
          while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
              http://${{ secrets.EC2_HOST }}/api/health || echo "000")
            
            if [ "$HTTP_CODE" = "200" ]; then
              echo "✅ Health check passed!"
              curl -s http://${{ secrets.EC2_HOST }}/api/health | jq .
              exit 0
            else
              echo "⏳ Health check failed (attempt $((RETRY_COUNT+1))/$MAX_RETRIES)"
              RETRY_COUNT=$((RETRY_COUNT+1))
              sleep 5
            fi
          done
          
          echo "❌ Health check failed after $MAX_RETRIES attempts"
          exit 1
      
      - name: Notify Deployment Success
        if: success()
        run: |
          echo "🎉 Deployment successful!"
          echo "Service URL: http://${{ secrets.EC2_HOST }}"
      
      - name: Notify Deployment Failure
        if: failure()
        run: |
          echo "❌ Deployment failed!"
          ssh ${{ secrets.EC2_USER }}@${{ secrets.EC2_HOST }} \
            "sudo journalctl -u vidp-aggregation -n 100 --no-pager"
```

### 7.3 Workflow pour les Tests Automatiques

Créez `.github/workflows/tests.yml` :

```yaml
name: Tests

on:
  push:
    branches: [ main, develop, staging ]
  pull_request:
    branches: [ main, develop ]

jobs:
  lint:
    name: Lint Code
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      
      - name: Install linting tools
        run: |
          pip install flake8 black isort mypy
      
      - name: Run Black
        run: black --check .
      
      - name: Run isort
        run: isort --check-only .
      
      - name: Run Flake8
        run: flake8 . --max-line-length=100 --exclude=venv

  test:
    name: Run Tests
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: ['3.10', '3.11']
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg
      
      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov pytest-mock
      
      - name: Run tests
        run: |
          pytest tests/ -v --cov=. --cov-report=xml --cov-report=html
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          flags: unittests
          name: codecov-umbrella

  security:
    name: Security Scan
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Bandit
        run: |
          pip install bandit
          bandit -r . -f json -o bandit-report.json || true
      
      - name: Run Safety
        run: |
          pip install safety
          safety check --json
```

### 7.4 Script de Déploiement Manuel (Backup)

Créez `scripts/deploy.sh` pour un déploiement manuel si nécessaire :

```bash
#!/bin/bash
# scripts/deploy.sh - Script de déploiement manuel

set -e

# Configuration
EC2_HOST="${EC2_HOST:-your-ec2-ip}"
EC2_USER="${EC2_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-vidp-ec2-key.pem}"
APP_DIR="/home/ubuntu/aggregation"

echo "=========================================="
echo "Manual Deployment to EC2"
echo "=========================================="
echo "Host: $EC2_HOST"
echo "User: $EC2_USER"
echo "=========================================="

# Fonction de logging
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Vérifier la connexion SSH
log "Testing SSH connection..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$EC2_USER@$EC2_HOST" "echo 'SSH connection successful'"

# Déployer le code
log "Deploying code..."
ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" << ENDSSH
    set -e
    cd $APP_DIR
    
    # Pull latest code
    git fetch origin
    git reset --hard origin/main
    
    # Activate venv
    source venv/bin/activate
    
    # Update dependencies
    pip install -r requirements.txt
    
    # Restart service
    sudo systemctl restart vidp-aggregation
    
    # Check status
    sleep 5
    sudo systemctl status vidp-aggregation --no-pager
ENDSSH

# Health check
log "Running health check..."
sleep 10
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://$EC2_HOST/api/health")

if [ "$HTTP_CODE" = "200" ]; then
    log "✅ Deployment successful!"
    curl -s "http://$EC2_HOST/api/health" | jq .
else
    log "❌ Health check failed (HTTP $HTTP_CODE)"
    exit 1
fi

log "=========================================="
log "Deployment complete!"
log "=========================================="
```

Rendre le script exécutable :

```bash
chmod +x scripts/deploy.sh
```

---

## 📊 Monitoring et Logs

### 8.1 Configuration CloudWatch Agent

```bash
# Installer CloudWatch Agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb

# Créer la configuration
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/config.json > /dev/null << 'EOF'
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "cwagent"
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/vidp-aggregation/*.log",
            "log_group_name": "/aws/ec2/vidp-aggregation",
            "log_stream_name": "{instance_id}/application",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/vidp-aggregation-access.log",
            "log_group_name": "/aws/ec2/vidp-aggregation",
            "log_stream_name": "{instance_id}/nginx-access",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/vidp-aggregation-error.log",
            "log_group_name": "/aws/ec2/vidp-aggregation",
            "log_stream_name": "{instance_id}/nginx-error",
            "timezone": "UTC"
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "VidpAggregation",
    "metrics_collected": {
      "cpu": {
        "measurement": [
          {"name": "cpu_usage_idle", "rename": "CPU_IDLE", "unit": "Percent"},
          {"name": "cpu_usage_iowait", "rename": "CPU_IOWAIT", "unit": "Percent"}
        ],
        "totalcpu": false
      },
      "disk": {
        "measurement": [
          {"name": "used_percent", "rename": "DISK_USED", "unit": "Percent"}
        ],
        "resources": ["*"]
      },
      "mem": {
        "measurement": [
          {"name": "mem_used_percent", "rename": "MEM_USED", "unit": "Percent"}
        ]
      }
    }
  }
}
EOF

# Démarrer CloudWatch Agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json
```

### 8.2 Script de Monitoring

Créez `scripts/monitor.sh` :

```bash
#!/bin/bash
# scripts/monitor.sh - Script de monitoring

echo "=========================================="
echo "VIDP Aggregation Service - Status"
echo "=========================================="

# Service status
echo -e "\n📊 Service Status:"
sudo systemctl status vidp-aggregation --no-pager | head -n 10

# CPU et Memory
echo -e "\n💻 System Resources:"
echo "CPU Usage:"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}'

echo "Memory Usage:"
free -h | awk 'NR==2{printf "Used: %s / %s (%.2f%%)\n", $3,$2,$3*100/$2 }'

echo "Disk Usage:"
df -h / | awk 'NR==2{printf "Used: %s / %s (%s)\n", $3,$2,$5}'

# Logs récents
echo -e "\n📝 Recent Logs (last 10 lines):"
sudo journalctl -u vidp-aggregation -n 10 --no-pager

# Network
echo -e "\n🌐 Network Connections:"
sudo netstat -tlpn | grep :8005

# Health check
echo -e "\n🏥 Health Check:"
curl -s http://localhost:8005/api/health | jq . || echo "Health check failed"

echo -e "\n=========================================="
```

### 8.3 Alertes CloudWatch

Créez des alarmes CloudWatch :

```bash
# Alarme CPU élevé
aws cloudwatch put-metric-alarm \
  --alarm-name vidp-ec2-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID

# Alarme disque plein
aws cloudwatch put-metric-alarm \
  --alarm-name vidp-ec2-disk-full \
  --alarm-description "Alert when disk usage exceeds 85%" \
  --metric-name DISK_USED \
  --namespace VidpAggregation \
  --statistic Average \
  --period 300 \
  --threshold 85 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2

# Alarme service down
aws cloudwatch put-metric-alarm \
  --alarm-name vidp-service-down \
  --alarm-description "Alert when service is down" \
  --metric-name StatusCheckFailed \
  --namespace AWS/EC2 \
  --statistic Maximum \
  --period 60 \
  --threshold 0 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --dimensions Name=InstanceId,Value=$INSTANCE_ID
```

---

## 🔒 Sécurité et Bonnes Pratiques

### 9.1 Configuration Fail2ban

```bash
# Installer Fail2ban
sudo apt-get install -y fail2ban

# Configurer pour SSH
sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
EOF

# Démarrer Fail2ban
sudo systemctl restart fail2ban
sudo systemctl enable fail2ban
```

### 9.2 Configuration UFW (Firewall)

```bash
# Installer UFW
sudo apt-get install -y ufw

# Configurer les règles
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS

# Activer le firewall
sudo ufw --force enable

# Vérifier le statut
sudo ufw status
```

### 9.3 Rotation des Logs

```bash
# Créer la configuration logrotate
sudo tee /etc/logrotate.d/vidp-aggregation > /dev/null << 'EOF'
/var/log/vidp-aggregation/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        sudo systemctl reload vidp-aggregation > /dev/null
    endscript
}

/var/log/nginx/vidp-aggregation-*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        sudo systemctl reload nginx > /dev/null
    endscript
}
EOF

# Tester la configuration
sudo logrotate -d /etc/logrotate.d/vidp-aggregation
```

### 9.4 Mises à Jour Automatiques de Sécurité

```bash
# Installer unattended-upgrades
sudo apt-get install -y unattended-upgrades

# Configurer
sudo dpkg-reconfigure -plow unattended-upgrades

# Vérifier la configuration
cat /etc/apt/apt.conf.d/50unattended-upgrades
```

---

## 🔄 Maintenance et Mises à Jour

### 10.1 Script de Backup

Créez `scripts/backup.sh` :

```bash
#!/bin/bash
# scripts/backup.sh - Script de sauvegarde

BACKUP_DIR="/var/backups/vidp-aggregation"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
S3_BACKUP_BUCKET="mon-bucket-vidp-backups"

echo "Starting backup at $TIMESTAMP..."

# Créer le répertoire de backup
sudo mkdir -p $BACKUP_DIR

# Backup de la configuration
echo "Backing up configuration..."
sudo tar -czf $BACKUP_DIR/config_$TIMESTAMP.tar.gz \
    /opt/vidp-aggregation/.env \
    /etc/nginx/sites-available/vidp-aggregation \
    /etc/systemd/system/vidp-aggregation.service

# Backup de la base de données DynamoDB (export)
echo "Exporting DynamoDB table..."
aws dynamodb scan \
    --table-name vidp-metadata \
    --output json > $BACKUP_DIR/dynamodb_$TIMESTAMP.json

# Upload vers S3
echo "Uploading to S3..."
aws s3 cp $BACKUP_DIR/ s3://$S3_BACKUP_BUCKET/backups/$TIMESTAMP/ --recursive

# Nettoyage des anciens backups (garder 7 jours)
find $BACKUP_DIR -type f -mtime +7 -delete

echo "Backup completed successfully!"
```

### 10.2 Script de Restauration

Créez `scripts/restore.sh` :

```bash
#!/bin/bash
# scripts/restore.sh - Script de restauration

BACKUP_TIMESTAMP=$1
S3_BACKUP_BUCKET="mon-bucket-vidp-backups"
RESTORE_DIR="/tmp/restore_$$"

if [ -z "$BACKUP_TIMESTAMP" ]; then
    echo "Usage: $0 <backup_timestamp>"
    exit 1
fi

echo "Restoring from backup: $BACKUP_TIMESTAMP"

# Créer répertoire temporaire
mkdir -p $RESTORE_DIR

# Télécharger depuis S3
aws s3 cp s3://$S3_BACKUP_BUCKET/backups/$BACKUP_TIMESTAMP/ $RESTORE_DIR/ --recursive

# Arrêter le service
sudo systemctl stop vidp-aggregation

# Restaurer la configuration
sudo tar -xzf $RESTORE_DIR/config_$BACKUP_TIMESTAMP.tar.gz -C /

# Restaurer DynamoDB (si nécessaire)
# aws dynamodb batch-write-item --request-items file://$RESTORE_DIR/dynamodb_$BACKUP_TIMESTAMP.json

# Redémarrer le service
sudo systemctl start vidp-aggregation

# Nettoyage
rm -rf $RESTORE_DIR

echo "Restore completed!"
```

### 10.3 Cron Jobs

```bash
# Configurer les tâches cron
crontab -e

# Ajouter les lignes suivantes:
# Backup quotidien à 2h du matin
0 2 * * * /opt/vidp-aggregation/scripts/backup.sh >> /var/log/vidp-backups.log 2>&1

# Monitoring toutes les 5 minutes
*/5 * * * * /opt/vidp-aggregation/scripts/monitor.sh >> /var/log/vidp-monitor.log 2>&1

# Nettoyage des fichiers temporaires tous les jours à 3h
0 3 * * * find /opt/vidp-aggregation/temp_aggregator -type f -mtime +1 -delete
```

---

## 🔍 Troubleshooting

### 11.1 Service ne démarre pas

```bash
# Vérifier les logs
sudo journalctl -u vidp-aggregation -n 100 --no-pager

# Vérifier les permissions
ls -la /opt/vidp-aggregation

# Vérifier FFmpeg
ffmpeg -version

# Tester manuellement
cd /opt/vidp-aggregation
source venv/bin/activate
python -c "from main import app; print('OK')"
```

### 11.2 Erreurs FFmpeg

```bash
# Vérifier l'installation FFmpeg
which ffmpeg
ffmpeg -version

# Réinstaller si nécessaire
sudo apt-get install --reinstall ffmpeg

# Vérifier les permissions sur les fichiers temporaires
ls -la /opt/vidp-aggregation/temp_aggregator
```

### 11.3 Problèmes S3/DynamoDB

```bash
# Tester la connexion S3
aws s3 ls s3://mon-bucket-vidp

# Tester DynamoDB
aws dynamodb describe-table --table-name vidp-metadata

# Vérifier les credentials
cat ~/.aws/credentials
```

### 11.4 Problèmes Nginx

```bash
# Tester la configuration
sudo nginx -t

# Voir les logs d'erreur
sudo tail -f /var/log/nginx/vidp-aggregation-error.log

# Redémarrer Nginx
sudo systemctl restart nginx
```

---

## 📋 Checklist de Déploiement

### Avant le déploiement

- [ ] Compte AWS configuré
- [ ] S3 Bucket créé et configuré
- [ ] DynamoDB Table créée avec indexes
- [ ] IAM User/Role créé avec bonnes permissions
- [ ] Instance EC2 lancée et accessible
- [ ] Elastic IP allouée (recommandé)
- [ ] Security Group configuré (ports 22, 80, 443, 8005)
- [ ] Nom de domaine configuré (optionnel)

### Installation sur EC2

- [ ] FFmpeg installé et testé
- [ ] Python 3.10+ installé
- [ ] Nginx installé et configuré
- [ ] AWS CLI configuré avec credentials
- [ ] Repository cloné
- [ ] Environnement virtuel créé
- [ ] Dépendances Python installées
- [ ] Fichier .env configuré
- [ ] Répertoires créés avec bonnes permissions

### Configuration des services

- [ ] Service systemd créé et activé
- [ ] Nginx configuré comme reverse proxy
- [ ] SSL/TLS configuré (Let's Encrypt)
- [ ] Firewall (UFW) configuré
- [ ] Fail2ban configuré
- [ ] CloudWatch Agent installé
- [ ] Rotation des logs configurée

### CI/CD

- [ ] Secrets GitHub configurés
- [ ] Workflow GitHub Actions créé
- [ ] Tests automatiques configurés
- [ ] Script de déploiement manuel créé
- [ ] Premier déploiement réussi
- [ ] Health checks fonctionnent

### Monitoring et Maintenance

- [ ] Alarmes CloudWatch configurées
- [ ] Scripts de backup configurés
- [ ] Cron jobs configurés
- [ ] Documentation à jour
- [ ] Équipe formée sur les procédures

---

## 🎉 Conclusion

Vous avez maintenant un déploiement complet sur EC2 avec :

✅ **Infrastructure AWS** : EC2, S3, DynamoDB
✅ **Application** : FastAPI + FFmpeg + Systemd
✅ **Reverse Proxy** : Nginx avec SSL
✅ **CI/CD** : GitHub Actions automatisé
✅ **Monitoring** : CloudWatch + Logs
✅ **Sécurité** : UFW + Fail2ban + SSL
✅ **Maintenance** : Backups + Scripts

### URLs Importantes

- **Application** : `http://your-domain.com` ou `http://your-elastic-ip`
- **API Docs** : `http://your-domain.com/docs`
- **Health Check** : `http://your-domain.com/api/health`
- **GitHub Actions** : `https://github.com/YOUR_USERNAME/YOUR_REPO/actions`

### Commandes Essentielles

```bash
# Déployer manuellement
./scripts/deploy.sh

# Vérifier le statut
sudo systemctl status vidp-aggregation

# Voir les logs
sudo journalctl -u vidp-aggregation -f

# Monitoring
./scripts/monitor.sh

# Backup
./scripts/backup.sh
```

---

**🚀 Votre microservice est maintenant en production sur AWS EC2 avec un pipeline CI/CD complet !**
