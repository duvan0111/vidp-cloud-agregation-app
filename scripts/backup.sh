#!/bin/bash
# scripts/backup.sh - Script de sauvegarde complète

set -e

# Configuration
BACKUP_DIR="/var/backups/vidp-aggregation"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
S3_BACKUP_BUCKET="${S3_BACKUP_BUCKET:-mon-bucket-vidp-backups}"
RETENTION_DAYS=7

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "   VIDP Aggregation - Backup Script"
echo "=========================================="
echo "Timestamp: $TIMESTAMP"
echo ""

# Créer le répertoire de backup
sudo mkdir -p $BACKUP_DIR

# ============================================================================
# Backup de la configuration
# ============================================================================

echo -e "${YELLOW}📁 Backing up configuration files...${NC}"

CONF_BACKUP="$BACKUP_DIR/config_$TIMESTAMP.tar.gz"

sudo tar -czf $CONF_BACKUP \
    /opt/vidp-aggregation/.env \
    /opt/vidp-aggregation/requirements.txt \
    /etc/nginx/sites-available/vidp-aggregation \
    /etc/systemd/system/vidp-aggregation.service \
    2>/dev/null || echo "Some files may not exist"

echo -e "${GREEN}✅ Configuration backup: $CONF_BACKUP${NC}"

# ============================================================================
# Backup du code source
# ============================================================================

echo -e "${YELLOW}📦 Backing up application code...${NC}"

cd /opt/vidp-aggregation
if [ -d .git ]; then
    # Sauvegarder le commit actuel
    git rev-parse HEAD > $BACKUP_DIR/commit_$TIMESTAMP.txt
    git log -1 --oneline > $BACKUP_DIR/commit_info_$TIMESTAMP.txt
    
    # Créer un bundle git
    git bundle create $BACKUP_DIR/repo_$TIMESTAMP.bundle --all
    
    echo -e "${GREEN}✅ Code backup: $BACKUP_DIR/repo_$TIMESTAMP.bundle${NC}"
else
    echo "No git repository found, creating archive..."
    sudo tar -czf $BACKUP_DIR/code_$TIMESTAMP.tar.gz \
        --exclude='venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='temp_aggregator/*' \
        --exclude='video_storage/*' \
        /opt/vidp-aggregation
    
    echo -e "${GREEN}✅ Code backup: $BACKUP_DIR/code_$TIMESTAMP.tar.gz${NC}"
fi

# ============================================================================
# Backup DynamoDB
# ============================================================================

echo -e "${YELLOW}☁️  Backing up DynamoDB table...${NC}"

DYNAMO_TABLE=$(grep DYNAMODB_TABLE_NAME /opt/vidp-aggregation/.env | cut -d'=' -f2)

if [ -n "$DYNAMO_TABLE" ]; then
    aws dynamodb scan \
        --table-name $DYNAMO_TABLE \
        --output json > $BACKUP_DIR/dynamodb_$TIMESTAMP.json
    
    # Compresser
    gzip $BACKUP_DIR/dynamodb_$TIMESTAMP.json
    
    echo -e "${GREEN}✅ DynamoDB backup: $BACKUP_DIR/dynamodb_$TIMESTAMP.json.gz${NC}"
else
    echo "DynamoDB table name not found in .env"
fi

# ============================================================================
# Backup des logs récents
# ============================================================================

echo -e "${YELLOW}📝 Backing up recent logs...${NC}"

if [ -d /var/log/vidp-aggregation ]; then
    sudo tar -czf $BACKUP_DIR/logs_$TIMESTAMP.tar.gz /var/log/vidp-aggregation
    echo -e "${GREEN}✅ Logs backup: $BACKUP_DIR/logs_$TIMESTAMP.tar.gz${NC}"
fi

# Backup des logs systemd
sudo journalctl -u vidp-aggregation --since "7 days ago" > $BACKUP_DIR/systemd_logs_$TIMESTAMP.log
gzip $BACKUP_DIR/systemd_logs_$TIMESTAMP.log
echo -e "${GREEN}✅ Systemd logs: $BACKUP_DIR/systemd_logs_$TIMESTAMP.log.gz${NC}"

# ============================================================================
# Créer un manifeste du backup
# ============================================================================

echo -e "${YELLOW}📋 Creating backup manifest...${NC}"

cat > $BACKUP_DIR/manifest_$TIMESTAMP.txt << EOF
VIDP Aggregation Service - Backup Manifest
==========================================

Backup Date: $(date)
Timestamp: $TIMESTAMP
Hostname: $(hostname)

Files Included:
---------------
$(ls -lh $BACKUP_DIR/*_$TIMESTAMP.* | awk '{print $9 " - " $5}')

System Information:
------------------
OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)
Kernel: $(uname -r)
Python: $(python3 --version)
FFmpeg: $(ffmpeg -version | head -n1)

Service Status:
--------------
$(systemctl status vidp-aggregation --no-pager | head -n 10)

Git Information:
---------------
$(cd /opt/vidp-aggregation && git log -1 --oneline 2>/dev/null || echo "No git info")
EOF

echo -e "${GREEN}✅ Manifest: $BACKUP_DIR/manifest_$TIMESTAMP.txt${NC}"

# ============================================================================
# Upload vers S3
# ============================================================================

echo ""
echo -e "${YELLOW}☁️  Uploading backups to S3...${NC}"

# Vérifier si le bucket existe
if aws s3 ls s3://$S3_BACKUP_BUCKET > /dev/null 2>&1; then
    aws s3 cp $BACKUP_DIR/ s3://$S3_BACKUP_BUCKET/backups/$TIMESTAMP/ \
        --recursive \
        --exclude "*" \
        --include "*_$TIMESTAMP.*"
    
    echo -e "${GREEN}✅ Uploaded to S3: s3://$S3_BACKUP_BUCKET/backups/$TIMESTAMP/${NC}"
else
    echo "⚠️  S3 bucket not found or not accessible: $S3_BACKUP_BUCKET"
    echo "   Backups saved locally only"
fi

# ============================================================================
# Nettoyage des anciens backups
# ============================================================================

echo ""
echo -e "${YELLOW}🗑️  Cleaning up old backups...${NC}"

# Supprimer les backups locaux plus vieux que RETENTION_DAYS
DELETED=$(find $BACKUP_DIR -type f -mtime +$RETENTION_DAYS -delete -print | wc -l)
echo "Deleted $DELETED old local backup files (older than $RETENTION_DAYS days)"

# Nettoyage S3 (optionnel)
if aws s3 ls s3://$S3_BACKUP_BUCKET > /dev/null 2>&1; then
    # Liste des backups S3 plus vieux que RETENTION_DAYS
    CUTOFF_DATE=$(date -d "$RETENTION_DAYS days ago" +%Y%m%d)
    
    aws s3 ls s3://$S3_BACKUP_BUCKET/backups/ | while read -r line; do
        BACKUP_DATE=$(echo $line | awk '{print $2}' | sed 's#/##' | cut -d'_' -f1)
        if [ "$BACKUP_DATE" -lt "$CUTOFF_DATE" ]; then
            BACKUP_PATH="s3://$S3_BACKUP_BUCKET/backups/$(echo $line | awk '{print $2}')"
            echo "  Deleting old S3 backup: $BACKUP_PATH"
            aws s3 rm $BACKUP_PATH --recursive --quiet
        fi
    done
fi

# ============================================================================
# Résumé du backup
# ============================================================================

echo ""
echo "=========================================="
echo "           BACKUP COMPLETED"
echo "=========================================="
echo ""
echo "Backup Location:"
echo "  Local:  $BACKUP_DIR"
echo "  S3:     s3://$S3_BACKUP_BUCKET/backups/$TIMESTAMP/"
echo ""
echo "Files created:"
ls -lh $BACKUP_DIR/*_$TIMESTAMP.* | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "Total backup size:"
du -sh $BACKUP_DIR | awk '{print "  " $1}'
echo ""
echo "To restore from this backup:"
echo "  ./scripts/restore.sh $TIMESTAMP"
echo ""
echo "=========================================="
