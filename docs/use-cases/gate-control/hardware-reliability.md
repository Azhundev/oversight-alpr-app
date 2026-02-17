# Hardware Reliability Guide (24/7 Operation)

**Created:** 2026-02-15
**Use Case:** Jetson devices running ALPR gate control continuously
**Related:** [Deployment Analysis](deployment-analysis.md) | [SaaS Business Model](saas-business-model.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Jetson Specifications](#jetson-specifications)
3. [Common Failure Points](#common-failure-points)
4. [Reliability Best Practices](#reliability-best-practices)
5. [Expected Reliability](#expected-reliability)
6. [Business Considerations](#business-considerations)
7. [Deployment Checklist](#deployment-checklist)
8. [Troubleshooting Guide](#troubleshooting-guide)

---

## Overview

Jetson devices are designed for industrial embedded use and 24/7 operation. With proper setup, they can run reliably for years. This guide covers the key considerations for production deployments.

**Bottom Line:** With best practices implemented, expect:
- **3-5% annual failure rate** (vs 15-25% without)
- **4-6+ years MTBF** (vs 1-2 years without)
- **Minutes to recover** (vs hours on-site)

---

## Jetson Specifications

### Hardware Capabilities

| Factor | Jetson Orin Nano | Jetson Orin NX |
|--------|------------------|----------------|
| **Design Target** | Industrial/embedded, 24/7 | Industrial/embedded, 24/7 |
| **Operating Temp** | -25°C to 80°C | -25°C to 80°C |
| **Storage Temp** | -40°C to 85°C | -40°C to 85°C |
| **Humidity** | 5% to 95% (non-condensing) | 5% to 95% (non-condensing) |
| **Power Consumption** | 7-15W | 10-25W |
| **MTBF (estimated)** | ~50,000+ hours | ~50,000+ hours |
| **Warranty** | 1 year (NVIDIA) | 1 year (NVIDIA) |

### Why Jetson is Suitable for 24/7

1. **No moving parts** - No fans on base module (dev kit has fan)
2. **Low power** - Less heat, less stress on components
3. **Industrial design** - Built for embedded applications
4. **ARM architecture** - Proven reliability in IoT/embedded

---

## Common Failure Points

### Failure Mode Analysis

| Risk | Likelihood | Typical Cause | Symptom | Impact |
|------|------------|---------------|---------|--------|
| **SD Card failure** | **HIGH** | Write cycle exhaustion | Boot failure, data corruption | System down |
| **Thermal throttling** | Medium | Poor ventilation | Slow performance, crashes | Degraded service |
| **Power surge damage** | Medium | Lightning, grid spikes | Won't power on | System down |
| **Software hang** | Low | Memory leak, bug | Unresponsive | Gate not working |
| **Network adapter** | Low | Static, power issues | No connectivity | No remote access |
| **eMMC/SSD failure** | Very Low | Age, defect | Boot failure | System down |
| **GPU/CPU failure** | Very Low | Defect, overheating | Won't boot | System down |

### The #1 Problem: SD Card Wear

**Why SD cards fail:**
- Consumer SD cards rated for ~10,000-100,000 write cycles
- 24/7 logging can exhaust this in 6-18 months
- Database writes, logs, and temp files accelerate wear

**Solution:** Always use NVMe SSD for production deployments.

```
SD Card lifespan:    ████░░░░░░░░░░░░░░░░  6-18 months
NVMe SSD lifespan:   ████████████████████  5-10+ years
```

---

## Reliability Best Practices

### 1. Storage: Use NVMe SSD (Critical)

**Never use SD cards for production deployments.**

| Storage Type | Write Endurance | Expected Life | Cost |
|--------------|-----------------|---------------|------|
| Consumer SD Card | 10K-100K cycles | 6-18 months | $15 |
| Industrial SD Card | 1M+ cycles | 2-3 years | $50 |
| **NVMe SSD** | 150-600 TBW | **5-10+ years** | **$35** |

**Recommended:**
- Samsung 980 256GB ($35) - 150 TBW rating
- WD Blue SN570 256GB ($30) - 150 TBW rating

**Installation:**
```bash
# Check current boot device
lsblk

# For NVMe boot, update /etc/fstab and boot configuration
# See Jetson documentation for NVMe boot setup
```

### 2. Power Protection

```
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐
│ Wall Power  │───→│  UPS + Surge    │───→│   Jetson    │
│  (Unstable) │    │  Protector      │    │   (Safe)    │
└─────────────┘    └─────────────────┘    └─────────────┘
```

**Why it matters:**
- Power surges can destroy electronics instantly
- Brown-outs cause filesystem corruption
- UPS provides graceful shutdown time

**Recommended UPS:**
| Model | Capacity | Runtime | Cost |
|-------|----------|---------|------|
| CyberPower CP425SLG | 425VA | 5-10 min | $40 |
| APC BE425M | 425VA | 5-10 min | $45 |
| CyberPower CP550SLG | 550VA | 10-15 min | $55 |

**Setup graceful shutdown:**
```bash
# Install apcupsd for UPS monitoring
sudo apt install apcupsd

# Configure /etc/apcupsd/apcupsd.conf
# Set BATTERYLEVEL to trigger shutdown
```

### 3. Thermal Management

**Temperature Monitoring:**
```bash
# Check current temperatures
cat /sys/devices/virtual/thermal/thermal_zone*/temp

# Or use tegrastats
tegrastats
```

**Thermal Guidelines:**

| Condition | CPU Temp | Action |
|-----------|----------|--------|
| Normal | <60°C | None needed |
| Warm | 60-75°C | Check ventilation |
| Hot | 75-85°C | Add cooling, reduce load |
| Throttling | >85°C | **Critical** - fix immediately |

**Best Practices:**
```
Good:    Ventilated enclosure, passive heatsink
Better:  Small fan + heatsink (included in dev kit)
Best:    Industrial enclosure with IP65 rating + thermal design
```

- Avoid sealed enclosures without ventilation
- Keep ambient temp below 50°C if possible
- Consider active cooling for hot environments

### 4. Watchdog & Auto-Recovery

**Systemd Service with Watchdog:**

```ini
# /etc/systemd/system/alpr-gate.service
[Unit]
Description=ALPR Gate Control Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=jetson
WorkingDirectory=/home/jetson/gate-control
ExecStart=/usr/bin/python3 pilot_lite.py
Restart=always
RestartSec=10
WatchdogSec=60
StandardOutput=journal
StandardError=journal

# Resource limits
MemoryMax=2G
CPUQuota=80%

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable alpr-gate.service
sudo systemctl start alpr-gate.service

# Check status
sudo systemctl status alpr-gate.service

# View logs
sudo journalctl -u alpr-gate.service -f
```

**Hardware Watchdog (Optional):**
```bash
# Enable hardware watchdog
sudo modprobe tegra_wdt

# Configure watchdog daemon
sudo apt install watchdog
# Edit /etc/watchdog.conf
```

### 5. Remote Monitoring

**Option A: Simple Ping Monitoring (Free)**
- UptimeRobot (free, 5-min intervals)
- Pingdom (free tier available)
- StatusCake (free tier)

**Setup:**
1. Create account at uptimerobot.com
2. Add HTTP monitor for `http://your-jetson-ip:8000/health`
3. Set alert threshold (e.g., 5 minutes)
4. Add email/SMS notifications

**Option B: Cloudflare Tunnel (Remote Access)**
```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
chmod +x cloudflared-linux-arm64
sudo mv cloudflared-linux-arm64 /usr/local/bin/cloudflared

# Login and create tunnel
cloudflared tunnel login
cloudflared tunnel create gate-control

# Run as service
sudo cloudflared service install
```

**Option C: Prometheus + Alertmanager**
For more advanced monitoring with metrics:
- Deploy Prometheus (can run on cloud portal)
- Scrape metrics from Jetson devices
- Configure alerts for device health

### 6. Automatic Updates

**Be careful with auto-updates in production!**

**Recommended approach:**
- **OS updates:** Manual, scheduled maintenance windows
- **ALPR software:** Push from cloud portal, staged rollout
- **Security patches:** Automatic for critical CVEs only

```bash
# Disable automatic apt updates
sudo systemctl disable apt-daily.timer
sudo systemctl disable apt-daily-upgrade.timer

# Create manual update script
#!/bin/bash
# /home/jetson/scripts/update.sh
sudo apt update
sudo apt upgrade -y
sudo reboot
```

---

## Expected Reliability

### With vs Without Best Practices

| Metric | Without Best Practices | With Best Practices |
|--------|------------------------|---------------------|
| **Annual failure rate** | 15-25% | 3-5% |
| **MTBF (estimated)** | 1-2 years | 4-6+ years |
| **Main failure cause** | SD card wear | Random component failure |
| **Recovery time** | Hours (on-site visit) | Minutes (remote restart or swap) |
| **Unplanned downtime** | Days per year | Hours per year |

### Reliability by Component

| Component | Failure Rate | With Mitigation |
|-----------|--------------|-----------------|
| SD Card | 50%/year | N/A (don't use) |
| NVMe SSD | <1%/year | <1%/year |
| Power-related | 10%/year | <2%/year (with UPS) |
| Thermal | 5%/year | <1%/year (proper cooling) |
| Software | 5%/year | <1%/year (watchdog) |
| Hardware defect | 2%/year | 2%/year |

---

## Business Considerations

### Spare Unit Strategy

For a SaaS business with multiple deployments:

| Deployed Units | Recommended Spares | Investment |
|----------------|-------------------|------------|
| 1-10 | 1 spare | $250 |
| 10-25 | 2 spares | $500 |
| 25-50 | 3-4 spares | $750-1000 |
| 50+ | 5% of fleet | Variable |

### Service Level Agreement (SLA)

| SLA Tier | Response Time | Resolution Time | Price Impact |
|----------|---------------|-----------------|--------------|
| Basic | 24 hours | 72 hours | Included |
| Standard | 4 hours | 24 hours | +$10/mo |
| Premium | 1 hour | 4 hours (swap) | +$30/mo |

### Replacement Process

**Remote-First Approach:**
1. Alert received (device offline)
2. Attempt remote restart via Cloudflare Tunnel
3. If failed, check power (ask customer)
4. If still failed, ship replacement unit
5. Customer swaps device
6. Return failed unit for diagnosis

**Quick-Swap Kit:**
- Pre-configured spare Jetson
- Customer-specific settings on USB drive
- Simple installation instructions
- Return shipping label

### Extended Warranty

NVIDIA offers extended warranty options:
- Standard: 1 year
- Extended: Up to 3 years (varies by region)

For business use, consider:
- Self-insuring (spare units) vs extended warranty
- Cost comparison based on fleet size

---

## Deployment Checklist

### Pre-Deployment

- [ ] NVMe SSD installed and tested (not SD card)
- [ ] Latest JetPack/L4T version installed
- [ ] ALPR software tested and working
- [ ] Network configuration (static IP or DHCP reservation)
- [ ] Remote access configured (Cloudflare Tunnel or VPN)

### Hardware Setup

- [ ] Quality power supply connected (official or equivalent)
- [ ] UPS/surge protector in place
- [ ] Proper ventilation ensured
- [ ] Cables secured and strain-relieved
- [ ] Enclosure appropriate for environment

### Software Setup

- [ ] Watchdog service configured
- [ ] Auto-restart on boot enabled
- [ ] Logging configured (with rotation)
- [ ] Health endpoint exposed
- [ ] Remote monitoring configured

### Post-Deployment

- [ ] Test reboot recovery
- [ ] Test power failure recovery (unplug and replug)
- [ ] Verify remote access works
- [ ] Confirm alerts are received
- [ ] Document any site-specific notes

---

## Troubleshooting Guide

### Device Won't Boot

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| No LEDs | Power issue | Check power supply, UPS |
| Green LED only | Boot device failure | Replace SSD/SD, reflash |
| Boot loop | Corrupted filesystem | Reflash, check power stability |
| Kernel panic | Hardware/software issue | Check logs, reflash |

### Device Offline (Was Working)

```
1. Ping the device
   └─ No response → Check power at site
   └─ Responds → SSH in, check services

2. Check service status
   sudo systemctl status alpr-gate
   └─ Not running → sudo systemctl restart alpr-gate
   └─ Running → Check logs

3. Check logs
   sudo journalctl -u alpr-gate -n 100
   └─ OOM killed → Increase memory limits
   └─ Exception → Bug in code, update software
```

### Performance Degraded

```
1. Check temperature
   tegrastats
   └─ >80°C → Improve cooling

2. Check memory
   free -h
   └─ High usage → Restart, check for leaks

3. Check disk
   df -h
   └─ >90% full → Clean logs, old data
```

### Gate Not Opening

```
1. Check ALPR service
   └─ Working → Check GPIO/relay

2. Check GPIO
   cat /sys/class/gpio/gpio18/value
   └─ Test relay manually

3. Check camera
   └─ Verify RTSP stream is accessible
```

---

## Maintenance Schedule

### Daily (Automated)

- Health check ping
- Log rotation
- Alert monitoring

### Weekly (Automated)

- Disk space check
- Memory usage trends
- Performance metrics review

### Monthly (Manual)

- Review error logs
- Check for software updates
- Verify backup/recovery process

### Quarterly (On-site if possible)

- Physical inspection
- Clean dust from enclosure
- Verify cable connections
- Test UPS battery

### Annually

- Consider hardware refresh (if >4 years old)
- Review and update SLA
- Performance baseline comparison

---

## Related Documentation

- [Project Structure](project-structure.md) - Single repository architecture (alpr-edge)
- [Modular Deployment](modular-deployment.md) - License-based module configuration
- [Deployment Analysis](deployment-analysis.md) - Technical deployment guide
- [SaaS Business Model](saas-business-model.md) - Multi-customer business model
- [Feature Tiers](feature-tiers.md) - Feature breakdown by tier
- [Use Case: Gate Control](use-case-gate-control.md) - Access control implementation
- [Use Case: Plate Logging](use-case-plate-logging.md) - Entry/exit logging (extends Gate Control)
- [Jetson Setup](../../jetson/JETSON_SETUP.md) - Initial Jetson configuration
