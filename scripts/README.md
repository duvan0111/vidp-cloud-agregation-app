# 🛠️ Scripts Utilitaires

Ce dossier contient les scripts de gestion et maintenance pour le déploiement EC2.

## 📋 Liste des Scripts

### 🚀 deploy.sh - Déploiement Manuel
Script complet de déploiement sur EC2 avec rollback automatique.

**Usage:**
```bash
# Définir les variables d'environnement
export EC2_HOST="your-ec2-ip"
export EC2_USER="ubuntu"
export SSH_KEY="path/to/vidp-ec2-key.pem"

# Exécuter le déploiement
./scripts/deploy.sh

# Ou en une ligne
EC2_HOST=54.123.45.67 EC2_USER=ubuntu SSH_KEY=vidp-ec2-key.pem ./scripts/deploy.sh
```

**Fonctionnalités:**
- ✅ Vérification des prérequis
- ✅ Test de connexion SSH
- ✅ Backup automatique avant déploiement
- ✅ Pull du code depuis Git
- ✅ Installation des dépendances
- ✅ Redémarrage du service
- ✅ Health check avec retry
- ✅ Rollback automatique en cas d'échec
- ✅ Nettoyage post-déploiement

### 📊 monitor.sh - Monitoring du Système
Script de monitoring complet affichant l'état du système et du service.

**Usage:**
```bash
# Sur l'instance EC2
./scripts/monitor.sh

# Via SSH depuis votre machine locale
ssh -i vidp-ec2-key.pem ubuntu@your-ec2-ip '/opt/vidp-aggregation/scripts/monitor.sh'
```

**Informations affichées:**
- 📊 Statut du service (running/stopped)
- 💻 Utilisation CPU, RAM, Disque
- 🌐 État réseau et connexions
- ☁️ Accès AWS (S3, DynamoDB)
- 📝 Logs récents
- ❌ Résumé des erreurs
- 💾 Utilisation du stockage
- 💡 Recommandations automatiques

### 💾 backup.sh - Sauvegarde Automatique
Script de backup complet avec upload vers S3.

**Usage:**
```bash
# Sur l'instance EC2
./scripts/backup.sh

# Avec bucket S3 personnalisé
S3_BACKUP_BUCKET=my-custom-bucket ./scripts/backup.sh
```

**Éléments sauvegardés:**
- 📁 Configuration (.env, nginx, systemd)
- 📦 Code source (git bundle)
- ☁️ Table DynamoDB
- 📝 Logs applicatifs et système
- 📋 Manifeste du backup

**Localisation des backups:**
- Local: `/var/backups/vidp-aggregation/`
- S3: `s3://mon-bucket-vidp-backups/backups/TIMESTAMP/`

**Rétention:** 7 jours (configurable)

## 🔄 Configuration des Cron Jobs

Pour automatiser les tâches, ajoutez ces lignes au crontab :

```bash
# Éditer le crontab
crontab -e

# Ajouter ces lignes:

# Backup quotidien à 2h du matin
0 2 * * * /opt/vidp-aggregation/scripts/backup.sh >> /var/log/vidp-backups.log 2>&1

# Monitoring toutes les heures
0 * * * * /opt/vidp-aggregation/scripts/monitor.sh >> /var/log/vidp-monitor.log 2>&1

# Nettoyage des fichiers temporaires tous les jours à 3h
0 3 * * * find /opt/vidp-aggregation/temp_aggregator -type f -mtime +1 -delete

# Health check toutes les 5 minutes avec alerte
*/5 * * * * curl -sf http://localhost:8005/api/health > /dev/null || echo "Service down!" | mail -s "ALERT: VIDP Service Down" admin@example.com
```

## 📝 Variables d'Environnement

### Pour deploy.sh

| Variable | Description | Exemple |
|----------|-------------|---------|
| `EC2_HOST` | IP ou domaine de l'instance EC2 | `54.123.45.67` |
| `EC2_USER` | Utilisateur SSH | `ubuntu` |
| `SSH_KEY` | Chemin vers la clé SSH | `vidp-ec2-key.pem` |
| `BRANCH` | Branche Git à déployer | `main` |

### Pour backup.sh

| Variable | Description | Défaut |
|----------|-------------|--------|
| `S3_BACKUP_BUCKET` | Bucket S3 pour les backups | `mon-bucket-vidp-backups` |
| `RETENTION_DAYS` | Nombre de jours de rétention | `7` |

## 🔧 Troubleshooting

### Script deploy.sh

**Problème:** `Permission denied (publickey)`
```bash
# Vérifier les permissions de la clé
chmod 400 vidp-ec2-key.pem

# Vérifier que la clé est correcte
ssh -i vidp-ec2-key.pem ubuntu@your-ec2-ip
```

**Problème:** Health check échoue
```bash
# Vérifier les logs sur EC2
ssh -i vidp-ec2-key.pem ubuntu@your-ec2-ip \
  'sudo journalctl -u vidp-aggregation -n 50 --no-pager'

# Vérifier que le service tourne
ssh -i vidp-ec2-key.pem ubuntu@your-ec2-ip \
  'sudo systemctl status vidp-aggregation'
```

### Script monitor.sh

**Problème:** `command not found: bc`
```bash
# Installer bc (calculatrice)
sudo apt-get install -y bc
```

**Problème:** Accès AWS échoue
```bash
# Vérifier les credentials AWS
aws configure list

# Tester l'accès S3
aws s3 ls

# Tester l'accès DynamoDB
aws dynamodb list-tables
```

### Script backup.sh

**Problème:** Upload S3 échoue
```bash
# Vérifier que le bucket existe
aws s3 ls s3://mon-bucket-vidp-backups

# Créer le bucket si nécessaire
aws s3 mb s3://mon-bucket-vidp-backups --region us-east-1
```

**Problème:** Backup trop volumineux
```bash
# Exclure les fichiers vidéo du backup
# (ils sont déjà sur S3)
# Modifier backup.sh pour exclure video_storage/
```

## 📚 Exemples d'Utilisation

### Déploiement complet depuis zéro

```bash
# 1. Configurer les variables
export EC2_HOST="54.123.45.67"
export EC2_USER="ubuntu"
export SSH_KEY="vidp-ec2-key.pem"

# 2. Première installation
ssh -i $SSH_KEY $EC2_USER@$EC2_HOST < deploy_ec2.sh

# 3. Déployer l'application
./scripts/deploy.sh

# 4. Vérifier avec le monitoring
ssh -i $SSH_KEY $EC2_USER@$EC2_HOST '/opt/vidp-aggregation/scripts/monitor.sh'
```

### Mise à jour de production

```bash
# 1. Créer un backup avant la mise à jour
ssh -i vidp-ec2-key.pem ubuntu@$EC2_HOST \
  '/opt/vidp-aggregation/scripts/backup.sh'

# 2. Déployer la nouvelle version
./scripts/deploy.sh

# 3. Surveiller pendant 5 minutes
watch -n 10 'ssh -i vidp-ec2-key.pem ubuntu@$EC2_HOST \
  "/opt/vidp-aggregation/scripts/monitor.sh"'
```

### Debugging en production

```bash
# 1. Vérifier le statut général
ssh -i vidp-ec2-key.pem ubuntu@$EC2_HOST \
  '/opt/vidp-aggregation/scripts/monitor.sh'

# 2. Suivre les logs en temps réel
ssh -i vidp-ec2-key.pem ubuntu@$EC2_HOST \
  'sudo journalctl -u vidp-aggregation -f'

# 3. Redémarrer si nécessaire
ssh -i vidp-ec2-key.pem ubuntu@$EC2_HOST \
  'sudo systemctl restart vidp-aggregation'

# 4. Vérifier que ça fonctionne
curl http://$EC2_HOST/api/health
```

## 🔗 Ressources Complémentaires

- [EC2_DEPLOYMENT_GUIDE.md](../EC2_DEPLOYMENT_GUIDE.md) - Guide complet de déploiement
- [EC2_QUICK_FIX.md](../EC2_QUICK_FIX.md) - Solutions rapides aux problèmes courants
- [DEPENDENCIES.md](../DEPENDENCIES.md) - Guide des dépendances

## 📞 Support

En cas de problème avec les scripts :

1. Vérifier les logs : `sudo journalctl -u vidp-aggregation -n 100`
2. Vérifier les permissions : `ls -la /opt/vidp-aggregation/scripts/`
3. Vérifier les variables d'environnement : `echo $EC2_HOST`
4. Consulter le guide de troubleshooting dans EC2_DEPLOYMENT_GUIDE.md
