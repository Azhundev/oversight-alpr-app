#!/usr/bin/env python3
"""
ALPR Service Manager
Enterprise-grade service orchestration with incremental startup support.

Features:
- RESTful API for service control (start/stop/restart/status)
- Service groups for incremental startup
- Real-time status monitoring via Docker API
- Memory usage tracking
- Audit logging
- Web dashboard with toggle controls
"""

import os
import subprocess
import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum
from pydantic import BaseModel
from loguru import logger
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse

# Docker SDK for Python
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger.warning("docker SDK not installed, using subprocess fallback")


# ============================================================================
# CONFIGURATION
# ============================================================================

class ServiceGroup(str, Enum):
    """Service groups for incremental startup"""
    KAFKA = "kafka"
    STORAGE = "storage"
    SEARCH = "search"
    ALERTS = "alerts"
    MONITORING = "monitoring"
    ANALYTICS = "analytics"
    OPTIONAL = "optional"


# Service definitions matching incremental-startup.md
SERVICE_GROUPS: Dict[str, List[str]] = {
    ServiceGroup.KAFKA: [
        "alpr-zookeeper",
        "alpr-kafka",
        "alpr-schema-registry",
    ],
    ServiceGroup.STORAGE: [
        "alpr-timescaledb",
        "alpr-minio",
        "alpr-kafka-consumer",
        # Note: query-api excluded - it hosts this dashboard!
    ],
    ServiceGroup.SEARCH: [
        "alpr-opensearch",
        "alpr-opensearch-dashboards",
        "alpr-elasticsearch-consumer",
    ],
    ServiceGroup.ALERTS: [
        "alpr-alert-engine",
    ],
    ServiceGroup.MONITORING: [
        "alpr-prometheus",
        "alpr-grafana",
        "alpr-loki",
        "alpr-promtail",
        "alpr-cadvisor",
        "alpr-node-exporter",
        "alpr-postgres-exporter",
        "alpr-kafka-exporter",
    ],
    ServiceGroup.ANALYTICS: [
        "alpr-metabase",
    ],
    ServiceGroup.OPTIONAL: [
        "alpr-kafka-ui",
    ],
}

# RAM estimates per group (MB)
RAM_ESTIMATES: Dict[str, int] = {
    ServiceGroup.KAFKA: 700,
    ServiceGroup.STORAGE: 200,
    ServiceGroup.SEARCH: 1500,
    ServiceGroup.ALERTS: 50,
    ServiceGroup.MONITORING: 700,
    ServiceGroup.ANALYTICS: 700,
    ServiceGroup.OPTIONAL: 200,
}

# Service dependencies
SERVICE_DEPENDENCIES: Dict[str, List[str]] = {
    ServiceGroup.STORAGE: [ServiceGroup.KAFKA],
    ServiceGroup.SEARCH: [ServiceGroup.KAFKA],
    ServiceGroup.ALERTS: [ServiceGroup.KAFKA],
    ServiceGroup.ANALYTICS: [ServiceGroup.STORAGE],
}


# ============================================================================
# MODELS
# ============================================================================

class ServiceStatus(BaseModel):
    """Individual service status"""
    name: str
    status: str  # running, stopped, starting, unhealthy
    health: Optional[str] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    uptime: Optional[str] = None
    ports: Optional[List[str]] = None


class GroupStatus(BaseModel):
    """Service group status"""
    group: str
    status: str  # running, partial, stopped
    services: List[ServiceStatus]
    total_memory_mb: float
    estimated_memory_mb: int
    running_count: int
    total_count: int


class SystemStatus(BaseModel):
    """Overall system status"""
    timestamp: str
    total_services: int
    running_services: int
    total_memory_mb: float
    groups: Dict[str, GroupStatus]
    pilot_ready: bool  # True if minimum services for pilot are running


class ActionResult(BaseModel):
    """Result of a service action"""
    action: str
    target: str
    success: bool
    message: str
    timestamp: str
    services_affected: List[str]


# ============================================================================
# SERVICE MANAGER CLASS
# ============================================================================

class ServiceManager:
    """
    Docker service manager with support for incremental startup.
    """

    def __init__(self, compose_file: str = "/home/jetson/OVR-ALPR/docker-compose.yml"):
        self.compose_file = compose_file
        self.compose_dir = os.path.dirname(compose_file)
        self.docker_client = None
        self.audit_log: List[Dict] = []

        if DOCKER_AVAILABLE:
            try:
                self.docker_client = docker.from_env()
                logger.info("Docker client initialized")
            except Exception as e:
                logger.warning(f"Docker client unavailable: {e}")

    def _log_action(self, action: str, target: str, result: str, user: str = "api"):
        """Log service action for audit trail"""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "target": target,
            "result": result,
            "user": user,
        }
        self.audit_log.append(entry)
        # Keep last 1000 entries
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]
        logger.info(f"Service action: {action} {target} -> {result}")

    def _get_all_memory_stats(self) -> Dict[str, float]:
        """Get memory usage for all containers at once (fast batch operation)"""
        try:
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.Name}}:{{.MemUsage}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                memory_map = {}
                for line in result.stdout.strip().split("\n"):
                    if ":" in line:
                        name, mem = line.split(":", 1)
                        # Parse memory like "56.38MiB / 7.441GiB"
                        mem_used = mem.split("/")[0].strip()
                        if "GiB" in mem_used:
                            memory_map[name] = float(mem_used.replace("GiB", "")) * 1024
                        elif "MiB" in mem_used:
                            memory_map[name] = float(mem_used.replace("MiB", ""))
                        elif "KiB" in mem_used:
                            memory_map[name] = float(mem_used.replace("KiB", "")) / 1024
                return memory_map
        except Exception as e:
            logger.debug(f"Could not get memory stats: {e}")
        return {}

    def get_container_stats(self, container_name: str, memory_map: Dict[str, float] = None) -> Optional[ServiceStatus]:
        """Get status for a single container (fast, non-blocking version)"""
        try:
            # Use docker CLI for fast status check (avoids blocking SDK calls)
            result = subprocess.run(
                ["docker", "inspect", "--format",
                 '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.StartedAt}}',
                 container_name],
                capture_output=True,
                text=True,
                timeout=2,  # 2 second timeout
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split("|")
                status = parts[0] if len(parts) > 0 else "unknown"
                health = parts[1] if len(parts) > 1 and parts[1] != "none" else None
                uptime = parts[2] if len(parts) > 2 else None

                # Get memory from pre-fetched map
                memory_mb = memory_map.get(container_name) if memory_map else None

                return ServiceStatus(
                    name=container_name,
                    status=status,
                    health=health,
                    memory_mb=round(memory_mb, 1) if memory_mb else None,
                    cpu_percent=None,
                    uptime=uptime,
                    ports=None,
                )
            else:
                return ServiceStatus(name=container_name, status="stopped")

        except subprocess.TimeoutExpired:
            return ServiceStatus(name=container_name, status="timeout")
        except Exception as e:
            logger.error(f"Error getting status for {container_name}: {e}")
            return ServiceStatus(name=container_name, status="unknown")

    def get_group_status(self, group: str, memory_map: Dict[str, float] = None) -> GroupStatus:
        """Get status for a service group"""
        services = SERVICE_GROUPS.get(group, [])
        service_statuses = []
        total_memory = 0.0
        running_count = 0

        for svc in services:
            status = self.get_container_stats(svc, memory_map)
            if status:
                service_statuses.append(status)
                if status.status == "running":
                    running_count += 1
                    if status.memory_mb:
                        total_memory += status.memory_mb

        # Determine group status
        if running_count == 0:
            group_status = "stopped"
        elif running_count == len(services):
            group_status = "running"
        else:
            group_status = "partial"

        return GroupStatus(
            group=group,
            status=group_status,
            services=service_statuses,
            total_memory_mb=round(total_memory, 1),
            estimated_memory_mb=RAM_ESTIMATES.get(group, 0),
            running_count=running_count,
            total_count=len(services),
        )

    def get_system_status(self) -> SystemStatus:
        """Get complete system status"""
        groups = {}
        total_running = 0
        total_services = 0
        total_memory = 0.0

        # Fetch all memory stats once (fast batch operation)
        memory_map = self._get_all_memory_stats()

        for group in ServiceGroup:
            group_status = self.get_group_status(group.value, memory_map)
            groups[group.value] = group_status
            total_running += group_status.running_count
            total_services += group_status.total_count
            total_memory += group_status.total_memory_mb

        # Check if minimum services for pilot are running (Kafka)
        kafka_status = groups.get(ServiceGroup.KAFKA)
        pilot_ready = kafka_status and kafka_status.status == "running"

        return SystemStatus(
            timestamp=datetime.utcnow().isoformat(),
            total_services=total_services,
            running_services=total_running,
            total_memory_mb=round(total_memory, 1),
            groups=groups,
            pilot_ready=pilot_ready,
        )

    async def start_group(self, group: str, check_deps: bool = True) -> ActionResult:
        """Start a service group"""
        if group not in [g.value for g in ServiceGroup]:
            return ActionResult(
                action="start",
                target=group,
                success=False,
                message=f"Unknown group: {group}",
                timestamp=datetime.utcnow().isoformat(),
                services_affected=[],
            )

        # Check dependencies
        if check_deps and group in SERVICE_DEPENDENCIES:
            for dep in SERVICE_DEPENDENCIES[group]:
                dep_status = self.get_group_status(dep)
                if dep_status.status != "running":
                    return ActionResult(
                        action="start",
                        target=group,
                        success=False,
                        message=f"Dependency not running: {dep}. Start it first or use force=true",
                        timestamp=datetime.utcnow().isoformat(),
                        services_affected=[],
                    )

        services = SERVICE_GROUPS.get(group, [])
        failed = []
        succeeded = []

        # Start each container directly using docker start
        for container in services:
            try:
                result = subprocess.run(
                    ["docker", "start", container],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    succeeded.append(container)
                else:
                    failed.append(f"{container}: {result.stderr.strip()}")
            except subprocess.TimeoutExpired:
                failed.append(f"{container}: timeout")
            except Exception as e:
                failed.append(f"{container}: {e}")

        success = len(failed) == 0
        if success:
            message = f"Started {len(succeeded)} services"
        else:
            message = f"Started {len(succeeded)}, failed {len(failed)}: {'; '.join(failed)}"

        self._log_action("start", group, "success" if success else "failed")

        return ActionResult(
            action="start",
            target=group,
            success=success,
            message=message,
            timestamp=datetime.utcnow().isoformat(),
            services_affected=succeeded,
        )

    async def stop_group(self, group: str) -> ActionResult:
        """Stop a service group"""
        if group not in [g.value for g in ServiceGroup]:
            return ActionResult(
                action="stop",
                target=group,
                success=False,
                message=f"Unknown group: {group}",
                timestamp=datetime.utcnow().isoformat(),
                services_affected=[],
            )

        services = SERVICE_GROUPS.get(group, [])
        failed = []
        succeeded = []

        # Stop each container directly using docker stop
        for container in services:
            try:
                result = subprocess.run(
                    ["docker", "stop", container],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    succeeded.append(container)
                else:
                    failed.append(f"{container}: {result.stderr.strip()}")
            except subprocess.TimeoutExpired:
                failed.append(f"{container}: timeout")
            except Exception as e:
                failed.append(f"{container}: {e}")

        success = len(failed) == 0
        if success:
            message = f"Stopped {len(succeeded)} services"
        else:
            message = f"Stopped {len(succeeded)}, failed {len(failed)}: {'; '.join(failed)}"

        self._log_action("stop", group, "success" if success else "failed")

        return ActionResult(
            action="stop",
            target=group,
            success=success,
            message=message,
            timestamp=datetime.utcnow().isoformat(),
            services_affected=succeeded,
        )

    async def restart_group(self, group: str) -> ActionResult:
        """Restart a service group"""
        stop_result = await self.stop_group(group)
        if not stop_result.success:
            return stop_result

        # Wait a moment for containers to stop
        await asyncio.sleep(2)

        return await self.start_group(group, check_deps=False)

    def get_audit_log(self, limit: int = 100) -> List[Dict]:
        """Get recent audit log entries"""
        return self.audit_log[-limit:]


# ============================================================================
# FASTAPI ROUTER
# ============================================================================

router = APIRouter(prefix="/services", tags=["Service Manager"])
manager = ServiceManager()


@router.get("/status", response_model=SystemStatus)
async def get_status():
    """
    Get complete system status including all service groups.

    Returns status, memory usage, and health for all services organized by group.
    """
    # Run blocking Docker calls in thread pool to avoid blocking event loop
    return await asyncio.to_thread(manager.get_system_status)


@router.get("/status/{group}", response_model=GroupStatus)
async def get_group_status_endpoint(group: str):
    """
    Get status for a specific service group.

    Groups: kafka, storage, search, alerts, monitoring, analytics, optional
    """
    if group not in [g.value for g in ServiceGroup]:
        raise HTTPException(status_code=404, detail=f"Unknown group: {group}")
    return await asyncio.to_thread(manager.get_group_status, group)


@router.post("/start/{group}", response_model=ActionResult)
async def start_group(group: str, force: bool = False):
    """
    Start a service group.

    By default, checks dependencies. Use force=true to skip dependency check.
    """
    return await manager.start_group(group, check_deps=not force)


@router.post("/stop/{group}", response_model=ActionResult)
async def stop_group(group: str):
    """
    Stop a service group.

    Warning: Stopping kafka will affect storage, search, and alerts.
    """
    return await manager.stop_group(group)


@router.post("/restart/{group}", response_model=ActionResult)
async def restart_group(group: str):
    """
    Restart a service group.
    """
    return await manager.restart_group(group)


@router.get("/audit")
async def get_audit_log(limit: int = 100):
    """
    Get recent service action audit log.
    """
    return {"entries": manager.get_audit_log(limit)}


@router.get("/groups")
async def list_groups():
    """
    List all service groups with their services and RAM estimates.
    """
    return {
        "groups": {
            group.value: {
                "services": SERVICE_GROUPS[group],
                "estimated_ram_mb": RAM_ESTIMATES.get(group, 0),
                "dependencies": SERVICE_DEPENDENCIES.get(group, []),
            }
            for group in ServiceGroup
        }
    }


# ============================================================================
# WEB DASHBOARD
# ============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ALPR Service Manager</title>
    <style>
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-card: #0f3460;
            --accent: #e94560;
            --success: #00d9a5;
            --warning: #ffc107;
            --text: #eee;
            --text-muted: #aaa;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text);
            min-height: 100vh;
            padding: 20px;
        }

        .header {
            text-align: center;
            margin-bottom: 30px;
        }

        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .status-bar {
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }

        .status-item {
            background: var(--bg-card);
            padding: 15px 25px;
            border-radius: 10px;
            text-align: center;
        }

        .status-item .value {
            font-size: 2rem;
            font-weight: bold;
        }

        .status-item .label {
            color: var(--text-muted);
            font-size: 0.9rem;
        }

        .groups-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }

        .group-card {
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }

        .group-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .group-title {
            font-size: 1.2rem;
            text-transform: capitalize;
        }

        .group-status {
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: bold;
        }

        .group-status.running { background: var(--success); color: #000; }
        .group-status.partial { background: var(--warning); color: #000; }
        .group-status.stopped { background: var(--accent); color: #fff; }

        .group-memory {
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 15px;
        }

        .services-list {
            margin-bottom: 15px;
        }

        .service-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }

        .service-name {
            font-size: 0.9rem;
        }

        .service-status {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }

        .status-dot.running { background: var(--success); }
        .status-dot.stopped { background: var(--accent); }
        .status-dot.unhealthy { background: var(--warning); }

        .service-memory {
            color: var(--text-muted);
            font-size: 0.8rem;
        }

        .group-actions {
            display: flex;
            gap: 10px;
        }

        .btn {
            flex: 1;
            padding: 10px;
            border: none;
            border-radius: 8px;
            font-weight: bold;
            cursor: pointer;
            transition: opacity 0.2s;
        }

        .btn:hover:not(:disabled) { opacity: 0.8; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .btn-start { background: var(--success); color: #000; }
        .btn-stop { background: var(--accent); color: #fff; }
        .btn-restart { background: var(--bg-card); color: var(--text); border: 1px solid rgba(255,255,255,0.2); }

        .refresh-bar {
            text-align: center;
            margin-top: 20px;
            color: var(--text-muted);
        }

        .loading {
            opacity: 0.5;
            pointer-events: none;
        }

    </style>
</head>
<body>
    <div class="header">
        <h1>ALPR Service Manager</h1>
        <p style="color: var(--text-muted);">Incremental startup control for RAM management</p>
    </div>

    <div class="status-bar" id="statusBar">
        <div class="status-item">
            <div class="value" id="runningCount">-</div>
            <div class="label">Services Running</div>
        </div>
        <div class="status-item">
            <div class="value" id="totalMemory">-</div>
            <div class="label">RAM Used / Budget</div>
        </div>
        <div class="status-item">
            <div class="value" id="pilotStatus">-</div>
            <div class="label">Pilot Ready</div>
        </div>
    </div>

    <div class="groups-grid" id="groupsGrid">
        <!-- Groups will be populated by JavaScript -->
    </div>

    <div class="refresh-bar">
        Auto-refresh every 10 seconds | <span id="lastUpdate">-</span>
    </div>

    <script>
        const API_BASE = '/services';

        async function fetchStatus() {
            try {
                const res = await fetch(`${API_BASE}/status`);
                return await res.json();
            } catch (e) {
                console.error('Failed to fetch status:', e);
                return null;
            }
        }

        async function performAction(action, group) {
            const card = document.querySelector(`[data-group="${group}"]`);
            if (!card) return;

            // Disable buttons during action
            const buttons = card.querySelectorAll('.btn');
            buttons.forEach(btn => btn.disabled = true);

            try {
                const res = await fetch(`${API_BASE}/${action}/${group}`, { method: 'POST' });
                const result = await res.json();

                if (!result.success) {
                    alert(`Action failed: ${result.message}`);
                }
            } catch (e) {
                alert(`Error: ${e.message}`);
            }

            // Always refresh after action (re-enables buttons based on state)
            setTimeout(refreshStatus, 1500);
        }

        function renderGroups(data) {
            const grid = document.getElementById('groupsGrid');
            const groupOrder = ['kafka', 'storage', 'search', 'alerts', 'monitoring', 'analytics', 'optional'];

            // Check if we need initial render
            if (grid.children.length === 0) {
                grid.innerHTML = groupOrder.map(groupName => `
                    <div class="group-card" data-group="${groupName}">
                        <div class="group-header">
                            <span class="group-title">${groupName}</span>
                            <span class="group-status" data-field="status"></span>
                        </div>
                        <div class="group-memory" data-field="memory"></div>
                        <div class="services-list" data-field="services"></div>
                        <div class="group-actions">
                            <button class="btn btn-start" onclick="performAction('start', '${groupName}')">Start</button>
                            <button class="btn btn-stop" onclick="performAction('stop', '${groupName}')">Stop</button>
                            <button class="btn btn-restart" onclick="performAction('restart', '${groupName}')">Restart</button>
                        </div>
                    </div>
                `).join('');
            }

            // Update each group incrementally
            groupOrder.forEach(groupName => {
                const group = data.groups[groupName];
                if (!group) return;

                const card = grid.querySelector(`[data-group="${groupName}"]`);
                if (!card) return;

                // Update status badge
                const statusEl = card.querySelector('[data-field="status"]');
                statusEl.className = `group-status ${group.status}`;
                statusEl.textContent = group.status;

                // Update memory
                const memoryEl = card.querySelector('[data-field="memory"]');
                memoryEl.textContent = `${group.total_memory_mb} MB used / ~${group.estimated_memory_mb} MB estimated`;

                // Update services list
                const servicesEl = card.querySelector('[data-field="services"]');
                servicesEl.innerHTML = group.services.map(svc => `
                    <div class="service-item">
                        <span class="service-name">${svc.name.replace('alpr-', '')}</span>
                        <div class="service-status">
                            ${svc.memory_mb ? `<span class="service-memory">${svc.memory_mb} MB</span>` : ''}
                            <span class="status-dot ${svc.health === 'unhealthy' ? 'unhealthy' : svc.status}"></span>
                        </div>
                    </div>
                `).join('');

                // Update button states
                const startBtn = card.querySelector('.btn-start');
                const stopBtn = card.querySelector('.btn-stop');
                const restartBtn = card.querySelector('.btn-restart');
                startBtn.disabled = group.status === 'running';
                stopBtn.disabled = group.status === 'stopped';
                restartBtn.disabled = group.status === 'stopped';
            });
        }

        function updateStatusBar(data) {
            document.getElementById('runningCount').textContent = `${data.running_services}/${data.total_services}`;
            // Calculate total estimated budget (sum of all group estimates)
            const totalBudget = Object.values(data.groups).reduce((sum, g) => sum + g.estimated_memory_mb, 0);
            document.getElementById('totalMemory').textContent = `${data.total_memory_mb.toFixed(0)} / ${totalBudget}`;
            document.getElementById('pilotStatus').textContent = data.pilot_ready ? '✅ Yes' : '❌ No';
            document.getElementById('pilotStatus').style.color = data.pilot_ready ? 'var(--success)' : 'var(--accent)';
            document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
        }

        async function refreshStatus() {
            const data = await fetchStatus();
            if (data) {
                updateStatusBar(data);
                renderGroups(data);
            }
        }

        // Initial load
        refreshStatus();

        // Auto-refresh every 10 seconds
        setInterval(refreshStatus, 10000);
    </script>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """
    Web dashboard for service management.

    Provides a visual interface with toggle controls for each service group.
    """
    return DASHBOARD_HTML
