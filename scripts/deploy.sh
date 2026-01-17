#!/bin/bash
# scripts/deploy.sh - Script de déploiement manuel sur EC2

set -e

# ============================================================================
# Configuration
# ============================================================================

# Variables d'environnement (peuvent être overridées)
EC2_HOST="${EC2_HOST:-your-ec2-ip-or-domain}"
EC2_USER="${EC2_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-vidp-ec2-key.pem}"
APP_DIR="/opt/vidp-aggregation"
BRANCH="${BRANCH:-main}"

# Couleurs pour l'output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Fonctions utilitaires
# ============================================================================

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# ============================================================================
# Validation des prérequis
# ============================================================================

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Vérifier que les variables sont définies
    if [ "$EC2_HOST" = "your-ec2-ip-or-domain" ]; then
        error "Please set EC2_HOST environment variable"
        echo "Usage: EC2_HOST=your-ip EC2_USER=ubuntu SSH_KEY=path/to/key.pem ./scripts/deploy.sh"
        exit 1
    fi
    
    # Vérifier que la clé SSH existe
    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found: $SSH_KEY"
        exit 1
    fi
    
    # Vérifier les permissions de la clé
    PERMS=$(stat -c %a "$SSH_KEY")
    if [ "$PERMS" != "400" ] && [ "$PERMS" != "600" ]; then
        warning "SSH key has incorrect permissions. Fixing..."
        chmod 400 "$SSH_KEY"
    fi
    
    success "Prerequisites check passed"
}

# ============================================================================
# Test de connexion SSH
# ============================================================================

test_ssh_connection() {
    log "Testing SSH connection to $EC2_USER@$EC2_HOST..."
    
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
       "$EC2_USER@$EC2_HOST" "echo 'SSH connection successful'" > /dev/null 2>&1; then
        success "SSH connection established"
    else
        error "Failed to connect to EC2 instance"
        exit 1
    fi
}

# ============================================================================
# Backup avant déploiement
# ============================================================================

create_backup() {
    log "Creating backup before deployment..."
    
    ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" << 'ENDSSH'
        BACKUP_DIR="/var/backups/vidp-aggregation"
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        
        sudo mkdir -p $BACKUP_DIR
        
        # Backup de la configuration actuelle
        if [ -f /opt/vidp-aggregation/.env ]; then
            sudo cp /opt/vidp-aggregation/.env $BACKUP_DIR/.env.$TIMESTAMP
        fi
        
        # Backup du code actuel
        cd /opt/vidp-aggregation
        if [ -d .git ]; then
            git rev-parse HEAD > $BACKUP_DIR/commit.$TIMESTAMP
        fi
        
        echo "Backup created at $BACKUP_DIR"
ENDSSH
    
    success "Backup created"
}

# ============================================================================
# Déploiement du code
# ============================================================================

deploy_code() {
    log "Deploying code from branch: $BRANCH..."
    
    ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" << ENDSSH
        set -e
        
        cd $APP_DIR
        
        # Afficher la version actuelle
        echo "Current version:"
        git log -1 --oneline || echo "No git history"
        
        # Fetch et pull
        echo ""
        echo "Pulling latest code..."
        git fetch origin
        git checkout $BRANCH
        git reset --hard origin/$BRANCH
        
        # Afficher la nouvelle version
        echo ""
        echo "New version:"
        git log -1 --oneline
ENDSSH
    
    success "Code deployed"
}

# ============================================================================
# Installation des dépendances
# ============================================================================

install_dependencies() {
    log "Installing/updating dependencies..."
    
    ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" << 'ENDSSH'
        set -e
        
        cd /opt/vidp-aggregation
        
        # Activer l'environnement virtuel
        source venv/bin/activate
        
        # Mettre à jour pip
        pip install --upgrade pip --quiet
        
        # Installer les dépendances
        pip install -r requirements.txt --quiet
        
        # Vérifier les dépendances critiques
        python check_dependencies.py
ENDSSH
    
    success "Dependencies installed"
}

# ============================================================================
# Redémarrage du service
# ============================================================================

restart_service() {
    log "Restarting service..."
    
    ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" << 'ENDSSH'
        sudo systemctl restart vidp-aggregation
        
        # Attendre que le service démarre
        sleep 5
        
        # Vérifier le statut
        if sudo systemctl is-active --quiet vidp-aggregation; then
            echo "Service restarted successfully"
        else
            echo "Service failed to start!"
            sudo journalctl -u vidp-aggregation -n 20 --no-pager
            exit 1
        fi
ENDSSH
    
    success "Service restarted"
}

# ============================================================================
# Health check
# ============================================================================

health_check() {
    log "Running health check..."
    
    local MAX_RETRIES=10
    local RETRY_COUNT=0
    local WAIT_TIME=3
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
            "http://$EC2_HOST/api/health" 2>/dev/null || echo "000")
        
        if [ "$HTTP_CODE" = "200" ]; then
            success "Health check passed!"
            
            # Afficher les infos du service
            HEALTH_INFO=$(curl -s "http://$EC2_HOST/api/health" 2>/dev/null)
            echo ""
            echo "Service Information:"
            echo "$HEALTH_INFO" | jq . 2>/dev/null || echo "$HEALTH_INFO"
            return 0
        else
            RETRY_COUNT=$((RETRY_COUNT+1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                warning "Health check failed (attempt $RETRY_COUNT/$MAX_RETRIES). Retrying in ${WAIT_TIME}s..."
                sleep $WAIT_TIME
            fi
        fi
    done
    
    error "Health check failed after $MAX_RETRIES attempts"
    
    # Afficher les logs en cas d'échec
    log "Showing recent logs:"
    ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" \
        "sudo journalctl -u vidp-aggregation -n 50 --no-pager"
    
    return 1
}

# ============================================================================
# Rollback
# ============================================================================

rollback() {
    error "Deployment failed. Rolling back..."
    
    ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" << 'ENDSSH'
        cd /opt/vidp-aggregation
        
        # Revenir au commit précédent
        git reset --hard HEAD@{1}
        
        # Redémarrer le service
        sudo systemctl restart vidp-aggregation
ENDSSH
    
    warning "Rollback completed. Please check the service status."
}

# ============================================================================
# Nettoyage post-déploiement
# ============================================================================

cleanup() {
    log "Cleaning up..."
    
    ssh -i "$SSH_KEY" "$EC2_USER@$EC2_HOST" << 'ENDSSH'
        # Nettoyer les fichiers temporaires
        find /opt/vidp-aggregation/temp_aggregator -type f -mtime +1 -delete 2>/dev/null || true
        
        # Nettoyer les anciens backups (garder 7 derniers)
        find /var/backups/vidp-aggregation -type f -mtime +7 -delete 2>/dev/null || true
ENDSSH
    
    success "Cleanup completed"
}

# ============================================================================
# Affichage des informations de déploiement
# ============================================================================

show_deployment_info() {
    echo ""
    echo "=========================================="
    echo "         DEPLOYMENT COMPLETED"
    echo "=========================================="
    echo ""
    echo "🌐 Service URL:       http://$EC2_HOST"
    echo "📚 API Documentation: http://$EC2_HOST/docs"
    echo "🏥 Health Check:      http://$EC2_HOST/api/health"
    echo ""
    echo "Useful commands:"
    echo "  Check status:  ssh -i $SSH_KEY $EC2_USER@$EC2_HOST 'sudo systemctl status vidp-aggregation'"
    echo "  View logs:     ssh -i $SSH_KEY $EC2_USER@$EC2_HOST 'sudo journalctl -u vidp-aggregation -f'"
    echo "  Monitor:       ssh -i $SSH_KEY $EC2_USER@$EC2_HOST '/opt/vidp-aggregation/scripts/monitor.sh'"
    echo ""
    echo "=========================================="
}

# ============================================================================
# Fonction principale
# ============================================================================

main() {
    echo ""
    echo "=========================================="
    echo "   VIDP Aggregation - Manual Deployment"
    echo "=========================================="
    echo ""
    echo "Target:  $EC2_USER@$EC2_HOST"
    echo "Branch:  $BRANCH"
    echo "SSH Key: $SSH_KEY"
    echo ""
    echo "=========================================="
    echo ""
    
    # Demander confirmation
    read -p "Do you want to proceed with the deployment? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        warning "Deployment cancelled by user"
        exit 0
    fi
    
    # Exécuter les étapes du déploiement
    check_prerequisites
    test_ssh_connection
    create_backup
    deploy_code
    install_dependencies
    restart_service
    
    # Health check avec gestion du rollback en cas d'échec
    if health_check; then
        cleanup
        show_deployment_info
        success "🎉 Deployment successful!"
        exit 0
    else
        rollback
        error "Deployment failed after rollback. Please check the logs."
        exit 1
    fi
}

# ============================================================================
# Gestion des signaux (Ctrl+C)
# ============================================================================

trap 'error "Deployment interrupted by user"; exit 130' INT

# ============================================================================
# Point d'entrée
# ============================================================================

main "$@"
