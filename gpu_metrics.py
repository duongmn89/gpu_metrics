import argparse
import sqlite3
import subprocess
import sys
import time
from prometheus_client import start_http_server, Gauge, REGISTRY
import os
import shlex

def run_nsys_profile(command, output_base):
    """Run nsys profile and export to SQLite"""
    # Step 1: Run nsys profile
    nsys_cmd = ["nsys", "profile", "--gpu-metrics-devices=all", "--force-overwrite=true","--gpu-metrics-frequency=99", "-o", output_base] + command
    try:
        proc = subprocess.Popen(nsys_cmd, stderr=subprocess.PIPE)
        _, err = proc.communicate()
        proc.kill()
        if proc.returncode != 0:
            print(f"Error running nsys profile: {err.decode()}")
            sys.exit(1)
    except Exception as e:
        print(f"Exception running nsys: {e}")
        sys.exit(1)

    # Step 2: Export to SQLite
    rep_file = f"{output_base}.nsys-rep"
    sqlite_file = f"{output_base}.sqlite"
    export_cmd = ["nsys", "export", "--force-overwrite=true", "-t", "sqlite", rep_file, "-o", sqlite_file]

    try:
        proc = subprocess.Popen(export_cmd, stderr=subprocess.PIPE)
        _, err = proc.communicate()
        proc.kill()
        if proc.returncode != 0:
            print(f"Error exporting to SQLite: {err.decode()}")
            sys.exit(1)
    except Exception as e:
        print(f"Exception exporting to SQLite: {e}")
        sys.exit(1)
    
    return sqlite_file

# def map_gpu_to_typeid(conn):
#     """Map GPU devices to metric typeIDs using device ID ordering"""
#     cur = conn.cursor()
#     cur.execute("SELECT id, name, busLocation, uuid FROM TARGET_INFO_GPU ORDER BY id")
#     gpus = cur.fetchall()
#     cur.execute("SELECT DISTINCT typeId FROM GPU_METRICS")
#     type_ids = sorted([row[0] for row in cur.fetchall()])
    
#     if len(gpus) != len(type_ids):
#         print(f"Warning: GPU count ({len(gpus)}) doesn't match typeID count ({len(type_ids)})")
    
#     # Map smallest typeID to lowest GPU ID
#     return {gpu[0]: (type_id, gpu[1], gpu[2], gpu[3]) 
#             for gpu, type_id in zip(gpus, type_ids)}


def map_gpu_to_typeid(conn):
    """Map GPU devices to metric typeIDs using the composite bit field structure"""
    cur = conn.cursor()
    
    # Get GPU information from TARGET_INFO_GPU
    cur.execute("SELECT id, name, busLocation, uuid FROM TARGET_INFO_GPU ORDER BY id")
    gpus = cur.fetchall()
    
    # Create a mapping of GPU IDs to GPU info
    gpu_info_map = {gpu[0]: (gpu[1], gpu[2], gpu[3]) for gpu in gpus}
    
    # Get distinct typeIds and extract GPU IDs
    cur.execute("SELECT DISTINCT typeId FROM GPU_METRICS")
    typeid_gpu_map = {}
    
    for row in cur.fetchall():
        type_id = row[0]
        # Extract GPU ID from the composite bit field (lower 8 bits)
        gpu_id = type_id & 0xFF
        
        # Verify the GPU ID exists in our GPU info map
        if gpu_id in gpu_info_map:
            name, bus, uuid = gpu_info_map[gpu_id]
            typeid_gpu_map[gpu_id] = (type_id, name, bus, uuid)
        else:
            print(f"Warning: GPU ID {gpu_id} not found in TARGET_INFO_GPU for typeId {type_id}")
    
    return typeid_gpu_map


def get_metric_name(conn, metricName):
    """Get human-readable metric name from metric ID"""
    
    cur = conn.cursor()
    like_pattern = f"%{metricName}%"
    #print(like_pattern)
    cur.execute("SELECT metricName, metricId FROM TARGET_INFO_GPU_METRICS WHERE metricName LIKE ? LIMIT 1", (like_pattern,))
    row = cur.fetchone()
    #print(row)
    #remove [] part of metric name
    if row:
        #print(row[0],row[1])
        return row
    else:
        return f"metric_{metricName}"

def process_metrics(conn, metricName, start_time=None, end_time=None):
    """Calculate average metric values per GPU"""
    gpu_map = map_gpu_to_typeid(conn)
    results = []

    for metric in metricName:
        metric_name, metric_id = get_metric_name(conn, metric)
        #print(metric_name, metric_id)
        
        for gpu_id, (type_id, name, bus, uuid) in gpu_map.items():
            query = """
                SELECT avg(value) 
                FROM GPU_METRICS 
                WHERE metricId = ? AND typeId = ?
            """
            params = [metric_id, type_id]
            
            if start_time is not None and end_time is not None:
                query += " AND timestamp BETWEEN ? AND ?"
                params.extend([start_time, end_time])
            
            cur = conn.cursor()
            cur.execute(query, params)
            values = [row[0] for row in cur.fetchall()]
            avg = sum(values) / len(values) if values else 0
            results.append((metric_name, gpu_id, name, bus, uuid, avg))
    
    return results


metrics_list = {}

def update_metrics(interval, sqlite, command, output, metric):
    while True:

        # Handle input sources
        if sqlite:
            sqlite_file = sqlite
        elif command and output:
            sqlite_file = run_nsys_profile(command, output)
        else:
            print("Error: Must provide either --sqlite or both --command and --output")
            sys.exit(1)
        

        global metrics_list
        
        # Process metrics
        try:
            with sqlite3.connect(sqlite_file) as conn:
                metrics = process_metrics(conn, metric)
                
                for name, gpu_id, gpu_name, bus, uuid, avg in metrics:
                    if name not in metrics_list:
                        metrics_list[name] = Gauge(
                            name.split(" [")[0].replace("/", "Or").replace(' ', '_').lower(),  # Metric name SMs Active [Throughput %] -> sms_active
                            name,  # Help text like SMs Active [Throughput %]
                            ['gpu','modelName','pci_bus_id','UUID']  # Labels for categorizing results
                        )
                    metrics_list[name].labels(gpu=str(gpu_id),modelName=gpu_name,pci_bus_id=bus,UUID=uuid).set(avg)

        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                print(f"Warning: {e} - Skipping interval")
            else:
                print(f"Database error: {e} - Skipping interval")
        except Exception as e:
            print(f"Unexpected error: {e} - Skipping interval")

        time.sleep(interval)


def start_prometheus(port, interval, sqlite, command, output, metric):
    start_http_server(port)
    print(f"Start prometheus export running on {port}")

    update_metrics(interval, sqlite, command, output, metric)
    


def main():
    # Replace argparse with environment variables
    args = {
        "command": shlex.split(os.getenv('COMMAND', 'echo')),
        "output": os.getenv('OUTPUT', 'report'),
        "sqlite": os.getenv('SQLITE'),
        "metric": [str(x) for x in os.getenv('METRIC', 'SMs Active,GR Active').split(',')],
        "port": int(os.getenv('PORT', '9401')),
        "interval": int(os.getenv('INTERVAL', '60'))
    }
    

    start_prometheus(args["port"], args["interval"], args["sqlite"], args["command"], args["output"], args["metric"])


if __name__ == "__main__":
    main()
