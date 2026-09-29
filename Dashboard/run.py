import os
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Redback SmartBike IoT Platform Diagnostic Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Web server bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")
    parser.add_argument("--broker", default=None, help="MQTT Broker hostname/IP override")
    parser.add_argument("--broker_port", type=int, default=None, help="MQTT Broker port override")
    parser.add_argument("--device", default=None, help="Default device ID override (e.g. 000001)")
    args = parser.parse_args()

    if args.broker:
        os.environ["MQTT_HOSTNAME"] = args.broker
    if args.broker_port:
        os.environ["MQTT_PORT"] = str(args.broker_port)
    if args.device:
        os.environ["DEVICE_ID"] = args.device

    # Ensure Dashboard directory is on python path
    dashboard_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, dashboard_dir)

    import uvicorn
    from server import app

    print(f"==================================================")
    print(f" Redback SmartBike IoT Dashboard starting on:")
    print(f" http://localhost:{args.port}")
    print(f"==================================================")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
