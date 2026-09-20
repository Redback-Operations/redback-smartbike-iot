
# Redback SmartBike IoT
IoT code for the Smartbike project (files for Bike 1)

An IoT control and telemetry platform for an indoor smart bike. The current
implementation connects Raspberry Pi/Linux hardware to Wahoo/KICKR equipment
and other sensors over Bluetooth Low Energy (BLE), moves readings and commands
through MQTT, and provides a browser dashboard for live monitoring and control.

> **Which code is current?** The working path is the Python code in
> [`Dashboard/`](./Dashboard/) and [`Drivers/`](./Drivers/). Material under
> [`Archive/`](./Archive/) is kept for reference and is not required by the
> current dashboard.

## Contents

- [What this project does](#what-this-project-does)
- [System architecture](#system-architecture)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [MQTT](#mqtt)
- [Running the hardware services](#running-the-hardware-services)
- [Dashboard API and browser connection](#dashboard-api-and-browser-connection)
- [Testing](#testing)
- [Repository map](#repository-map)
- [Archived applications](#archived-applications)
- [Troubleshooting and known limitations](#troubleshooting-and-known-limitations)

## What this project does

The platform brings together:

- Wahoo/KICKR smart-trainer telemetry: speed, cadence, power, incline, and
  resistance.
- Heart-rate monitoring.
- Fan/headwind control.
- GPIO button input for steering and braking.
- Structured workouts including endurance, ramped, strength, and threshold
  sessions.
- MQTT commands and reports using a per-bike topic namespace.
- A FastAPI dashboard with live WebSocket updates and HTTP control endpoints.

The dashboard keeps the latest values in memory. It is a live control surface,
not a historical data store, so restarting it clears the current telemetry
state.

## System architecture

```text
Wahoo/KICKR and BLE sensors
            |
            | Bluetooth Low Energy / GATT
            v
Python drivers on Raspberry Pi/Linux
            |
            | MQTT publish and subscribe
            v
        MQTT broker
            |
            +--> Dashboard (FastAPI)
            |       +--> HTTP control endpoints
            |       +--> WebSocket telemetry to the browser
            |
            +--> Fan, trainer, workout, button, and sensor services
```

Typical data flow:

1. A BLE device produces a reading.
2. A driver decodes the GATT characteristic.
3. The driver publishes a JSON reading to `bike/<DEVICE_ID>/...`.
4. The dashboard subscribes to the bike namespace and parses the message.
5. The dashboard broadcasts state and changes to connected browsers over a
   WebSocket.
6. A dashboard control is published as an MQTT command.
7. The appropriate driver receives the command and applies it to the hardware.

The central MQTT constants and hardware identifiers are in
[`Drivers/lib/constants.py`](./Drivers/lib/constants.py). The shared Paho
wrapper is [`Drivers/lib/mqtt_client.py`](./Drivers/lib/mqtt_client.py).

## Requirements

### Recommended setup: Raspberry Pi with Linux

For a real bike installation, use a Raspberry Pi running Linux. You will need:

- Python 3.9 or newer.
- A working Bluetooth adapter and permission to access BLE devices.
- The Wahoo/KICKR trainer or climb hardware used by the installation.
- Any additional heart-rate, cadence, fan, and GPIO hardware you want to run.
- A reachable MQTT broker and credentials if the broker requires them.
- The Linux system packages and permissions required by the GATT and GPIO
  libraries.

The MAC addresses in [`Drivers/lib/constants.py`](./Drivers/lib/constants.py)
are installation-specific. Replace them when fitting a different trainer or
sensor set.

### Using the project on other operating systems

The dashboard and its parsing test are also useful on a development computer.

| Platform | Dashboard | Parsing test | Complete physical bike |
| --- | --- | --- | --- |
| Raspberry Pi/Linux | Recommended | Supported | Recommended |
| macOS | Supported | Supported | Not the supported deployment path |
| Windows | Supported | Supported | Not supported by the current GATT/GPIO code |

macOS and Windows can connect to the same MQTT broker and display data
published by the Raspberry Pi. They are also suitable for changing the web
UI, testing payload parsing, and developing integrations. The supplied
`*.sh` launchers and the GPIO/BLE deployment code are Linux-oriented.

### Python dependencies

The dashboard dependencies are listed in
[`Dashboard/requirements.txt`](./Dashboard/requirements.txt):

- FastAPI
- Uvicorn
- Paho MQTT
- WebSockets
- python-dotenv

The hardware drivers may require additional system-level Bluetooth/GATT and
GPIO packages depending on the Raspberry Pi image and the service being run.

## Quick start

There are two sensible ways to run the project:

1. **Full Raspberry Pi installation:** run the dashboard and the hardware
   drivers on the Pi.
2. **Development computer:** run only the dashboard and tests on Windows or
   macOS, while the Pi (or another Linux host) runs the hardware drivers.

The commands below start the dashboard. Driver processes are separate and are
described in [Running the hardware services](#running-the-hardware-services).

### 1. Create a virtual environment

Run these commands from the repository root. The virtual environment lives in
[`Dashboard/`](./Dashboard/).

#### Raspberry Pi/Linux

```bash
cd Dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd ..
```

#### macOS

```bash
cd Dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd ..
```

#### Windows PowerShell

```powershell
cd Dashboard
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd ..
```

If PowerShell blocks script activation, either allow scripts for the current
user with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or run the
dashboard with the virtual-environment interpreter directly:

```powershell
.\Dashboard\.venv\Scripts\python.exe Dashboard\run.py --host 0.0.0.0 --port 8080
```

#### Windows Command Prompt

```bat
cd Dashboard
py -3 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd ..
```

Keep the environment activated for the remaining commands. On the Pi, use
the same terminal session when starting the dashboard and drivers. On macOS
or Windows, the dashboard can run locally and subscribe to a broker hosted on
the Pi or elsewhere.

### 2. Create local configuration

Copy [`.env.example`](./.env.example) to `.env` and fill in the broker and
device details. Use the command for your shell:

**Raspberry Pi/Linux and macOS:**
```bash
cp .env.example .env
```

**Windows PowerShell:**
```powershell
Copy-Item .env.example .env
```

**Windows Command Prompt:**
```bat
copy .env.example .env
```

The dashboard loads environment variables from the process environment and
also attempts to load a repository-root `.env`. Never commit `.env` or put
real broker passwords in `.env.example`.

### 3. Start the dashboard

From the repository root, with the virtual environment activated:

```bash
python Dashboard/run.py --host 0.0.0.0 --port 8080
```

On Windows PowerShell:

```powershell
python Dashboard\run.py --host 0.0.0.0 --port 8080
```

Open <http://localhost:8080>. If the dashboard is running on the Raspberry Pi,
open the same port from another computer using the Pi's address:

```text
http://<PI_IP>:8080
```

Command-line options can override the broker and bike for a single run:

```bash
python Dashboard/run.py \
  --broker 192.168.1.100 \
  --broker_port 1883 \
  --device 000002
```

On Windows PowerShell, keep the command on one line or use PowerShell's
backtick for continuation:

```powershell
python Dashboard\run.py --broker 192.168.1.100 --broker_port 1883 --device 000002
```

The dashboard process can start without a working broker, but live telemetry
and real hardware control require a reachable broker and running driver
services.

## Configuration

The complete starter list is in [`.env.example`](./.env.example). Variables
are grouped below by how they are used.

### Active dashboard and driver settings

| Variable | Purpose | Example |
| --- | --- | --- |
| `MQTT_HOSTNAME` | Primary MQTT broker hostname or IP address. | `localhost` |
| `MQTT_PORT` | MQTT listener port. | `1883` |
| `MQTT_USERNAME` | Broker username, if authentication is enabled. | *(blank)* |
| `MQTT_PASSWORD` | Broker password, if authentication is enabled. | *(blank)* |
| `MQTT_USE_TLS` | Enables dashboard TLS when `true`, `1`, or `yes`. Port `8883` also enables it. | `false` |
| `DEVICE_ID` | Bike identifier used in MQTT topics. | `000001` |
| `KICKR_MAC_ADDRESS` | KICKR address used by `scripts/start_kickr.sh`. | `AA:BB:CC:DD:EE:FF` |

The dashboard accepts these compatibility aliases when the primary name is
not present:

| Alias | Replaces |
| --- | --- |
| `MQTT_HOST` | `MQTT_HOSTNAME` |
| `MQTT_USER` | `MQTT_USERNAME` |
| `MQTT_PASS` | `MQTT_PASSWORD` |
| `BIKEID` | `DEVICE_ID` |

For the dashboard, the defaults are `localhost`, `1883`, empty credentials,
TLS disabled, and device `000001`. Several hardware drivers expect their
configuration to be present more strictly than the dashboard does, so set the
values explicitly when running the drivers.

### Archived IP updater settings

These are only relevant to the archived utility under
[`Archive/IPUpdater/`](./Archive/IPUpdater/):

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram/bot integration token. |
| `ETH0_IP` | Ethernet address state used by the updater. |
| `WLAN0_IP` | Wireless address state used by the updater. |

They are included in `.env.example` so an operator can see every environment
variable referenced anywhere in the repository. They are not needed for the
active dashboard.

## MQTT

### Broker connection

The dashboard subscribes with QoS 1 to:

```text
bike/#
Turn/#
$SYS/broker/uptime
```

The shared driver client uses Paho MQTT v5, username/password authentication,
QoS 1, and reconnect handling. Note that the dashboard and shared driver
client currently handle TLS differently: the dashboard enables it
conditionally, while [`Drivers/lib/mqtt_client.py`](./Drivers/lib/mqtt_client.py)
calls `tls_set()` for driver connections. Test TLS settings with the actual
broker before deploying the full driver stack.

### Topic convention

The normal namespace is:

```text
bike/<DEVICE_ID>/<measurement-or-command>
```

For example, with `DEVICE_ID=000001`:

| Direction | Topic | Meaning |
| --- | --- | --- |
| Command | `bike/000001/incline/control` | Set trainer incline |
| Command | `bike/000001/resistance/control` | Set trainer resistance |
| Command | `bike/000001/fan/control` | Set fan level |
| Command | `bike/000001/workout` | Start or control a workout |
| Report | `bike/000001/incline/report` | Incline telemetry |
| Report | `bike/000001/resistance/report` | Resistance telemetry |
| Report | `bike/000001/speed/report` | Speed telemetry |
| Report | `bike/000001/cadence/report` | Cadence telemetry |
| Report | `bike/000001/power/report` | Power telemetry |
| Report | `bike/000001/heartrate` | Heart-rate telemetry |
| Report | `bike/000001/fan/status` | Fan status |
| Report | `bike/000001/button/report` | Button, steering, or brake state |

Some active drivers publish the measurement without `/report`, for example
`bike/<DEVICE_ID>/speed` or `bike/<DEVICE_ID>/power`. The dashboard parser
recognises both forms. `Turn/Left` and `Turn/Right` are legacy steering topics
also consumed by the dashboard.

### Payloads

The standard telemetry payload produced by the smartbike driver is:

```json
{
  "value": 7.5,
  "unitName": "m/s",
  "timestamp": 1720000000.0,
  "metadata": {
    "deviceName": "raspberry-pi-hostname"
  }
}
```

Common units are:

| Measurement | Unit |
| --- | --- |
| Speed | `m/s` |
| Cadence | `RPM` |
| Power | `W` |
| Heart rate | `BPM` |
| Resistance | `percentage` |
| Incline | `degree` |
| Fan/headwind | `percentage` |

The parser also supports specialised payloads such as:

```json
{"incline": 4.5}
```

```json
{
  "resistance": 40,
  "target_power_watts": 160,
  "ftp_percent": 70,
  "workout": "endurance",
  "stage": "active"
}
```

```json
{"button": "LEFT", "state": 1}
```

### Publishing manually

The dashboard exposes a raw publish endpoint for development and integration
testing. Use the dashboard's documented API routes in
[`Dashboard/server.py`](./Dashboard/server.py), and avoid sending arbitrary
hardware commands to a live bike unless the command and value are understood.

## Running the hardware services

The Python services under [`Drivers/`](./Drivers/) are intentionally separate:
run only the services supported by the hardware attached to the Raspberry Pi.

| Folder | Responsibility |
| --- | --- |
| [`Drivers/smartbike/`](./Drivers/smartbike/) | Main Wahoo/smartbike controller and telemetry reporting |
| [`Drivers/kickr_climb_and_smart_trainer/`](./Drivers/kickr_climb_and_smart_trainer/) | KICKR incline, resistance, speed, cadence, and power |
| [`Drivers/cadence_sensor/`](./Drivers/cadence_sensor/) | BLE cadence acquisition and MQTT publishing |
| [`Drivers/heart_rate_sensor/`](./Drivers/heart_rate_sensor/) | Heart-rate acquisition and MQTT publishing |
| [`Drivers/fan/`](./Drivers/fan/) | Fan control and status publishing |
| [`Drivers/button_control/`](./Drivers/button_control/) | GPIO buttons, steering, and braking messages |
| [`Drivers/workouts/`](./Drivers/workouts/) | Endurance, ramped, strength, and threshold workouts |

The shell launchers in [`scripts/`](./scripts/) are intended for the original
Linux/Raspberry Pi deployment. They are not directly executable from Windows
or macOS because they use Bash, Linux paths, and Linux BLE/GPIO tooling. On
Linux they commonly expect:

```bash
source ~/.env
```

and a checkout at `~/iot`. Before using one, inspect its command and update
the path for the current checkout. Several launchers refer to historical
locations such as `Drivers/smartbike_driver`, `Drivers/wahoo_controller`,
`Drivers/FTP`, or `Drivers/Threshold_workout`, which do not all match the
current folder layout.

On macOS or Windows, start the dashboard normally and run compatible Python
driver modules manually where supported. For a complete physical bike setup,
deploy the drivers on the Linux/Raspberry Pi host rather than trying to run
these shell scripts locally.

Available launcher intentions include:

- `start_all.sh` and `start_smartbike.sh`: smartbike controller.
- `start_kickr.sh`: KICKR climb/trainer.
- `start_cadence.sh`: cadence sensor.
- `start_heartrate.sh`: heart-rate sensor.
- `start_fan.sh`: fan.
- `start_button_control.sh`: GPIO controls.
- `start_wahoo_controller.sh` and `start_workout.sh`: Wahoo/workout control.
- `start_ftp_workout.sh` and `start_threshold_workout.sh`: workout variants.

The BLE helper under [`scripts/ble-auto-connect/`](./scripts/ble-auto-connect/)
uses Linux shell/Expect automation and is not a native Windows workflow.

## Dashboard API and browser connection

The active web service is split into:

- [`Dashboard/run.py`](./Dashboard/run.py): command-line entry point.
- [`Dashboard/server.py`](./Dashboard/server.py): FastAPI application, MQTT
  connection, state parsing, WebSocket broadcasting, and control routes.
- [`Dashboard/static/index.html`](./Dashboard/static/index.html): page markup.
- [`Dashboard/static/app.js`](./Dashboard/static/app.js): browser MQTT-state
  presentation and controls through the HTTP/WebSocket API.
- [`Dashboard/static/style.css`](./Dashboard/static/style.css): dashboard
  styling.

The UI presents speed, cadence, power, heart rate, incline, resistance, fan,
workout, steering, brake, and MQTT connection information. It receives live
state through WebSockets and sends controls through FastAPI endpoints.

## Testing

Run the focused dashboard parsing test from the repository root. It works on
Linux, macOS, and Windows and does not need a live broker:

```bash
python Dashboard/tests/test_dashboard.py
```

Windows PowerShell equivalent:

```powershell
python Dashboard\tests\test_dashboard.py
```

This test exercises MQTT payload parsing and delta detection. It does not
require a live broker, BLE devices, GPIO, or a running dashboard.

There is no repository-wide build pipeline. The only GitHub Actions workflow
is [`security-scan.yml`](./.github/workflows/security-scan.yml).

## Repository map

### Active top-level areas

| Path | What it contains |
| --- | --- |
| [`.github/`](./.github/) | GitHub Actions security scanning workflow |
| [`Dashboard/`](./Dashboard/) | Active FastAPI dashboard, static frontend, requirements, and tests |
| [`Drivers/`](./Drivers/) | Active Python hardware drivers, MQTT helpers, constants, and workouts |
| [`scripts/`](./scripts/) | Raspberry Pi/Linux startup and BLE automation scripts |
| [`mqtt-testing-application/`](./mqtt-testing-application/) | Experimental MQTT publisher/listener clients |
| [`Archive/`](./Archive/) | Superseded applications, prototypes, research, and deployment material |
| [`LICENSE`](./LICENSE) | Repository license |

### Shared driver library

[`Drivers/lib/`](./Drivers/lib/) contains shared MQTT, BLE/GATT, constants,
device-address, range, and unit definitions. Reuse these definitions when
adding a driver instead of duplicating topic or payload conventions.

### Workouts

The active workout implementations are:

- [`Drivers/workouts/endurance_workouts/`](./Drivers/workouts/endurance_workouts/)
- [`Drivers/workouts/ramped_workouts/`](./Drivers/workouts/ramped_workouts/)
- [`Drivers/workouts/strength_workouts/`](./Drivers/workouts/strength_workouts/)
- [`Drivers/workouts/threshold_workouts/`](./Drivers/workouts/threshold_workouts/)

### Archive

[`Archive/`](./Archive/) is intentionally separated from the active runtime:

| Path | Purpose |
| --- | --- |
| [`Archive/Cycling Prototype/`](./Archive/Cycling%20Prototype/) | Early Arduino/ESP32/cycling prototype |
| [`Archive/Database/`](./Archive/Database/) | Earlier database schema material |
| [`Archive/Drivers/`](./Archive/Drivers/) | Earlier Python, Node.js, GUI, sensor, and workout drivers |
| [`Archive/IPUpdater/`](./Archive/IPUpdater/) | IP reporting/updater utility |
| [`Archive/MQTT/`](./Archive/MQTT/) | Earlier Node MQTT broker/client/discovery work |
| [`Archive/old-code/`](./Archive/old-code/) | Superseded C++/C# and sensor code |
| [`Archive/Repcount and Flex Sensor Prototype/`](./Archive/Repcount%20and%20Flex%20Sensor%20Prototype/) | Flex-sensor and repetition-count experiments |
| [`Archive/Research/`](./Archive/Research/) | Cycling, sensor, exercise, and smartwatch research |
| [`Archive/sensors-backend/`](./Archive/sensors-backend/) | Archived TypeScript/Express/MongoDB/MQTT backend |
| [`Archive/sensors-cms-frontend/`](./Archive/sensors-cms-frontend/) | Archived React administration frontend |
| [`Archive/T3_2023/`](./Archive/T3_2023/) | Older sensor and MQTT experiments |
| [`Archive/Unity/`](./Archive/Unity/) | Unity cycling visualisation prototype |

The archived backend and frontend have their own `package.json` files and can
be run independently, but doing so is outside the active dashboard path.

## Archived applications

For reference only:

### Archived TypeScript backend

From [`Archive/sensors-backend/`](./Archive/sensors-backend/):

```bash
npm install
npm run build
npm start
```

Development and data commands are also defined in its `package.json`:

```bash
npm run dev
npm run iot-data-processor
npm run seed-bikes-data
npm run seed-devices-data
npm run seed-sensors-data
```

Its stack includes TypeScript, Express, MongoDB/Mongoose, and MQTT. The
`npm test` script is a placeholder that intentionally exits with
`Error: no test specified`.

### Archived React frontend

From [`Archive/sensors-cms-frontend/`](./Archive/sensors-cms-frontend/):

```bash
npm install
npm start
npm run build
npm test
```

This is a separate React 18 application using Material UI, Axios, Recharts,
React Router, and an MQTT client package.

## Troubleshooting and known limitations

### Dashboard starts but no live values appear

Check the following in order:

1. The MQTT broker is reachable from the machine running the dashboard.
2. `MQTT_HOSTNAME`, `MQTT_PORT`, credentials, and `DEVICE_ID` are correct.
3. The relevant BLE/GPIO driver is running and connected to its hardware.
4. The driver is publishing under the same `DEVICE_ID` namespace.
5. The browser is connected to the dashboard WebSocket.

### BLE devices do not connect

Confirm Linux Bluetooth permissions, adapter availability, device pairing, and
the hardware addresses in [`Drivers/lib/constants.py`](./Drivers/lib/constants.py).
Those addresses are installation-specific and must be changed for another
bike or sensor set.

### MQTT topics look inconsistent

The repository contains both `/report` and shorter measurement topics, plus
legacy `Turn/...` topics. The dashboard intentionally parses several of these
forms. New integrations should prefer:

```text
bike/<DEVICE_ID>/<measurement>/report
```

for telemetry and:

```text
bike/<DEVICE_ID>/<command>/control
```

for commands.

### Startup scripts fail with “file not found”

The scripts were written for an earlier `~/iot` deployment and some contain
historical paths. Run the underlying Python module directly from the current
checkout, or update the script path for the installed layout.

### Security and operational notes

- Keep real credentials in a local `.env` or protected deployment secret.
- Do not commit `.env`, broker passwords, or bot tokens.
- MQTT credentials may be exposed in process arguments by legacy scripts.
- The dashboard has no persistent telemetry database.
- Do not expose the control dashboard to an untrusted network without adding
  authentication and transport security.

## License

See [`LICENSE`](./LICENSE).
