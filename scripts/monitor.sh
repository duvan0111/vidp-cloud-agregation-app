#!/bin/bash
# scripts/monitor.sh - Script de monitoring complet

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

clear

echo -e "${BLUE}=========================================="
echo "   VIDP Aggregation - System Monitor"
echo "==========================================${NC}"
echo ""
date
echo ""

# ============================================================================
# Service Status
# ============================================================================

echo -e "${YELLOW}📊 SERVICE STATUS${NC}"
echo "----------------------------------------"

if sudo systemctl is-active --quiet vidp-aggregation; then
    echo -e "${GREEN}✅ Service: RUNNING${NC}"
    UPTIME=$(systemctl show vidp-aggregation --property=ActiveEnterTimestamp --value)
    echo "   Uptime: $UPTIME"
else
    echo -e "${RED}❌ Service: STOPPED${NC}"
fi

# Process info
PID=$(pgrep -f "uvicorn main:app" | head -n 1)
if [ -n "$PID" ]; then
    echo "   PID: $PID"
    MEM=$(ps -p $PID -o rss= | awk '{printf "%.2f MB", $1/1024}')
    CPU=$(ps -p $PID -o %cpu= | awk '{print $1"%"}')
    echo "   Memory: $MEM"
    echo "   CPU: $CPU"
fi

echo ""

# ============================================================================
# System Resources
# ============================================================================

echo -e "${YELLOW}💻 SYSTEM RESOURCES${NC}"
echo "----------------------------------------"

# CPU
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
echo -e "CPU Usage:    ${CPU_USAGE}%"

if (( $(echo "$CPU_USAGE > 80" | bc -l) )); then
    echo -e "              ${RED}⚠️  High CPU usage!${NC}"
fi

# Memory
MEM_INFO=$(free | awk 'NR==2{printf "%.2f%%", $3*100/$2 }')
MEM_DETAILS=$(free -h | awk 'NR==2{printf "%s / %s", $3,$2}')
echo -e "Memory Usage: $MEM_INFO ($MEM_DETAILS)"

if (( $(echo "$MEM_INFO > 85" | bc -l) )); then
    echo -e "              ${RED}⚠️  High memory usage!${NC}"
fi

# Disk
DISK_USAGE=$(df -h / | awk 'NR==2{print $5}')
DISK_DETAILS=$(df -h / | awk 'NR==2{printf "%s / %s", $3,$2}')
echo -e "Disk Usage:   $DISK_USAGE ($DISK_DETAILS)"

DISK_PCT=$(echo $DISK_USAGE | sed 's/%//')
if [ "$DISK_PCT" -gt 85 ]; then
    echo -e "              ${RED}⚠️  Low disk space!${NC}"
fi

echo ""

# ============================================================================
# Network
# ============================================================================

echo -e "${YELLOW}🌐 NETWORK${NC}"
echo "----------------------------------------"

# Port 8005
if netstat -tlnp 2>/dev/null | grep -q ':8005'; then
    echo -e "${GREEN}✅ Port 8005: LISTENING${NC}"
else
    echo -e "${RED}❌ Port 8005: NOT LISTENING${NC}"
fi

# Connexions actives
CONNECTIONS=$(netstat -an | grep ':8005' | grep ESTABLISHED | wc -l)
echo "   Active connections: $CONNECTIONS"

# Test local
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/api/health 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Health check: OK${NC}"
else
    echo -e "${RED}❌ Health check: FAILED (HTTP $HTTP_CODE)${NC}"
fi

echo ""

# ============================================================================
# AWS Services
# ============================================================================

echo -e "${YELLOW}☁️  AWS SERVICES${NC}"
echo "----------------------------------------"

# S3
S3_BUCKET=$(grep S3_BUCKET_NAME /opt/vidp-aggregation/.env 2>/dev/null | cut -d'=' -f2)
if [ -n "$S3_BUCKET" ]; then
    if aws s3 ls s3://$S3_BUCKET > /dev/null 2>&1; then
        echo -e "${GREEN}✅ S3 Bucket: $S3_BUCKET${NC}"
        OBJECT_COUNT=$(aws s3 ls s3://$S3_BUCKET --recursive | wc -l)
        echo "   Objects: $OBJECT_COUNT"
    else
        echo -e "${RED}❌ S3 Bucket: Cannot access $S3_BUCKET${NC}"
    fi
fi

# DynamoDB
DYNAMO_TABLE=$(grep DYNAMODB_TABLE_NAME /opt/vidp-aggregation/.env 2>/dev/null | cut -d'=' -f2)
if [ -n "$DYNAMO_TABLE" ]; then
    if aws dynamodb describe-table --table-name $DYNAMO_TABLE > /dev/null 2>&1; then
        echo -e "${GREEN}✅ DynamoDB: $DYNAMO_TABLE${NC}"
        ITEM_COUNT=$(aws dynamodb scan --table-name $DYNAMO_TABLE --select "COUNT" --output json 2>/dev/null | jq -r '.Count')
        echo "   Items: $ITEM_COUNT"
    else
        echo -e "${RED}❌ DynamoDB: Cannot access $DYNAMO_TABLE${NC}"
    fi
fi

echo ""

# ============================================================================
# Recent Logs
# ============================================================================

echo -e "${YELLOW}📝 RECENT LOGS (last 10 lines)${NC}"
echo "----------------------------------------"
sudo journalctl -u vidp-aggregation -n 10 --no-pager | sed 's/^/   /'

echo ""

# ============================================================================
# Error Summary
# ============================================================================

echo -e "${YELLOW}❌ ERROR SUMMARY (last hour)${NC}"
echo "----------------------------------------"
ERROR_COUNT=$(sudo journalctl -u vidp-aggregation --since "1 hour ago" | grep -i error | wc -l)

if [ "$ERROR_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✅ No errors in the last hour${NC}"
else
    echo -e "${RED}⚠️  $ERROR_COUNT errors found${NC}"
    echo ""
    echo "Recent errors:"
    sudo journalctl -u vidp-aggregation --since "1 hour ago" | grep -i error | tail -n 5 | sed 's/^/   /'
fi

echo ""

# ============================================================================
# Storage Usage
# ============================================================================

echo -e "${YELLOW}💾 STORAGE USAGE${NC}"
echo "----------------------------------------"

# Temp directory
TEMP_DIR="/opt/vidp-aggregation/temp_aggregator"
if [ -d "$TEMP_DIR" ]; then
    TEMP_SIZE=$(du -sh $TEMP_DIR 2>/dev/null | cut -f1)
    TEMP_FILES=$(find $TEMP_DIR -type f | wc -l)
    echo "Temp directory: $TEMP_SIZE ($TEMP_FILES files)"
fi

# Video storage
VIDEO_DIR="/opt/vidp-aggregation/video_storage"
if [ -d "$VIDEO_DIR" ]; then
    VIDEO_SIZE=$(du -sh $VIDEO_DIR 2>/dev/null | cut -f1)
    VIDEO_FILES=$(find $VIDEO_DIR -type f | wc -l)
    echo "Video storage:  $VIDEO_SIZE ($VIDEO_FILES files)"
fi

# Logs
LOG_SIZE=$(sudo du -sh /var/log/vidp-aggregation 2>/dev/null | cut -f1)
if [ -n "$LOG_SIZE" ]; then
    echo "Logs:           $LOG_SIZE"
fi

echo ""

# ============================================================================
# Recommendations
# ============================================================================

echo -e "${YELLOW}💡 RECOMMENDATIONS${NC}"
echo "----------------------------------------"

RECOMMENDATIONS=0

# High CPU
if (( $(echo "$CPU_USAGE > 80" | bc -l) )); then
    echo "⚠️  High CPU usage detected. Consider scaling up or optimizing."
    RECOMMENDATIONS=$((RECOMMENDATIONS + 1))
fi

# High Memory
MEM_PCT=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ "$MEM_PCT" -gt 85 ]; then
    echo "⚠️  High memory usage. Consider increasing instance size."
    RECOMMENDATIONS=$((RECOMMENDATIONS + 1))
fi

# Disk space
if [ "$DISK_PCT" -gt 85 ]; then
    echo "⚠️  Low disk space. Clean up old files or increase volume size."
    RECOMMENDATIONS=$((RECOMMENDATIONS + 1))
fi

# Errors
if [ "$ERROR_COUNT" -gt 10 ]; then
    echo "⚠️  High error rate. Check logs: sudo journalctl -u vidp-aggregation -f"
    RECOMMENDATIONS=$((RECOMMENDATIONS + 1))
fi

# Service not running
if ! sudo systemctl is-active --quiet vidp-aggregation; then
    echo "❌ Service is not running. Start with: sudo systemctl start vidp-aggregation"
    RECOMMENDATIONS=$((RECOMMENDATIONS + 1))
fi

if [ "$RECOMMENDATIONS" -eq 0 ]; then
    echo -e "${GREEN}✅ All systems operational!${NC}"
fi

echo ""
echo "=========================================="
echo -e "${BLUE}Monitoring completed at $(date +%H:%M:%S)${NC}"
echo "=========================================="
echo ""
echo "Useful commands:"
echo "  View logs:    sudo journalctl -u vidp-aggregation -f"
echo "  Restart:      sudo systemctl restart vidp-aggregation"
echo "  Check status: sudo systemctl status vidp-aggregation"
echo ""
