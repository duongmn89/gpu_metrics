# GPU Profile Metrics Exporter

A lightweight Prometheus exporter that collects **NVIDIA GPU performance metrics** using **Nsight Systems (nsys)** and exposes them via an HTTP endpoint.  
The tool can either:
- Run live GPU profiling with `nsys profile` at a defined interval or
- Parse existing Nsight Systems `.sqlite` reports.

This allows you to continuously monitor GPU utilization, throughput, and other hardware metrics in **Prometheus** and visualize them in **Grafana**.

---

##  Features

- Automated GPU metric collection using `nsys`
- Supports both static `.sqlite` files and live profiling commands
- Exposes metrics in Prometheus format
- Configurable collection interval and metric selection
- Easy to deploy with Docker

---

##  Requirements

- **NVIDIA GPU**
- **Nsight Systems CLI** (`nsys`)  
  The Docker image installs this automatically.
- **Python 3.8+**
- **Prometheus client library**

---

##  Run with Docker

### 1. Build the image

```bash
docker build -t gpu-metrics-exporter .
```

### 2. Run container

This will continuously run an nsys profile for your command and export metrics to Prometheus.

```bash
docker run --gpus all -p 9401:9401 \
  -e COMMAND="echo" \
  -e OUTPUT="report" \
  -e METRIC="SMs Active,GR Active" \
  -e INTERVAL=60 \
  -e PORT=9401 \
  gpu-metrics-exporter

```

Metrics will be available at

```bash
http://localhost:9401/metrics
```

Environment Variables

| Variable | Description | Default |
|-----------|-------------|----------|
| `COMMAND` | Command to profile with Nsight Systems (used when `SQLITE` is not set) | `echo` |
| `OUTPUT` | Output base name for generated `.nsys-rep` and `.sqlite` files | `report` |
| `SQLITE` | Path to an existing Nsight Systems SQLite file (skips live profiling) | *(none)* |
| `METRIC` | Comma-separated list of metric names to export (partial match supported) | `SMs Active,GR Active` |
| `PORT` | HTTP port for Prometheus metrics | `9401` |
| `INTERVAL` | Seconds between metric collection | `60` |


Example Prometheus Metric Output

```bash
# HELP sms_active SMs Active [Throughput %]
# TYPE sms_active gauge
sms_active{gpu="0",modelName="NVIDIA RTX A6000",pci_bus_id="0000:41:00.0",UUID="GPU-xxxx"} 87.5

# HELP gr_active GR Active [Throughput %]
# TYPE gr_active gauge
gr_active{gpu="0",modelName="NVIDIA RTX A6000",pci_bus_id="0000:41:00.0",UUID="GPU-xxxx"} 75.3

```

##  Run with Kubernetes

In order to run in Kubernetes environment, the container need to use privileged mode and request resources nvidia.com/gpu

For example:

```bash
      containers:
      - name: gpu-metrics
        image: gpu-metrics-exporter
        securityContext:
          privileged: true
        resources:
          limits:
            nvidia.com/gpu: 1
```
Because it will consume 1 GPU resource => Should be run in shared GPU env only. 
