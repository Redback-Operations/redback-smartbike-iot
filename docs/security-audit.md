# Security Audit — IoT / SmartbikeVR

Date: 2026-08-09
Scope: `Drivers/`, `scripts/`, `mqtt-testing-application/`, `.github/workflows/`, repo-wide secret/dependency hygiene.
Method: manual review (no SecDevOps meeting notes were available at time of writing; this audit was run independently to unblock the "Security in IoT" task).

## What's already solid

- MQTT credentials (`MQTT_USERNAME` / `MQTT_PASSWORD`) are read from environment variables everywhere, never hardcoded, across `fan`, `cadence_sensor`, `heart_rate_sensor`, `smartbike`, `kickr_climb_and_smart_trainer`, and `workouts` drivers.
- The shared `Drivers/lib/mqtt_client.py` base class enables TLS (`tls_set`) before connecting, and every driver-specific MQTT client (`fan`, `cadence_sensor`, `heart_rate_sensor`, `smartbike`, `kickr`) extends it rather than rolling its own insecure connection.
- No use of `eval`, `os.system`, `shell=True`, or unsafe `pickle.load` found in active driver/script code.
- `scripts/*.service` systemd units run as the unprivileged `pi` user, not root.
- CI already runs Bandit (SAST) and Safety (dependency CVEs) on every PR via `.github/workflows/security-scan.yml`.
- Pi remote access requires the Deakin VPN before SSH is reachable (per `Archive/docs/pi-remote-access-guide.md`).

## Findings & recommended tasks

### Critical

0. **Unauthenticated MQTT command path to physical actuators.** `Drivers/smartbike/smartbike.py` (`Climber.on_message` / `Resistance.on_message`) accepts resistance/incline commands from `bike/<device_id>/resistance/control` and `/incline/control` with only a numeric range check — no verification of *who* sent the command. The code itself has a `# TODO: add error checking and reporting for converting from str to dict` at this exact point, i.e. it's known-unfinished. Per the driver READMEs, devices connect to one HiveMQ Cloud broker with topics keyed only by a sequential `device_id` (`bike/000001/...`); there's no documented broker-side ACL restricting a credential to its own device's topics. Net effect: anyone holding a valid MQTT credential can potentially publish control commands to **any** bike, changing resistance/incline while someone is mid-ride. This is a physical-safety issue, not just a data-confidentiality one, and is almost certainly what prompted the "severely lacks security" note.
   → **Task (urgent, needs broker + firmware work, not just a repo edit):**
   - Configure per-device HiveMQ Cloud credentials scoped by ACL so each device can only publish/subscribe to its own `bike/<device_id>/#` namespace.
   - Add command authentication (e.g. a shared secret/HMAC per command, or short-lived signed tokens from the backend) so the driver rejects commands not issued by the legitimate control plane, not just anyone on the topic.
   - Add the missing error handling on malformed/unauthorized payloads (the existing TODO) so bad input fails closed, not silently.
   - This was not fixed in this pass — it requires broker configuration and a protocol decision the team needs to make, not something to change unilaterally in code.

### High priority

1. **CI workflow uses `pull_request_target` with full checkout of the PR head.**
   `.github/workflows/security-scan.yml` triggers on `pull_request_target` (runs with base-branch permissions/secrets) but checks out `github.event.pull_request.head.sha` — attacker-controlled code from a fork PR. Combined with broad permissions (`issues: write`, `checks: write`, `security-events: write`, `statuses: write`), this is a known pattern for secret exfiltration / repo compromise via a malicious PR, even though this workflow doesn't currently reference secrets.
   → **Task:** switch trigger to `pull_request` and trim permissions to only what's used (`contents: read`, `pull-requests: write`). *(Fixed in this pass — see below.)*

2. **`node_modules/` (72,000+ files) is committed to git** under `Archive/sensors-backend` and `Archive/sensors-cms-frontend`, despite `node_modules/` being listed in `.gitignore`. This means the ignore rule was added after these directories were already tracked, so it's not actually taking effect for them. This bloats the repo, makes dependency provenance hard to audit, and can silently carry vulnerable/malicious packages into version control.
   → **Task:** `git rm -r --cached Archive/sensors-backend/node_modules Archive/sensors-cms-frontend/node_modules` and commit. *(Not done automatically — this rewrites a large chunk of tracked history and should be coordinated with the team before pushing.)*

### Medium priority

3. **No repo-level guard against committing `.env` files.** `.gitignore` doesn't exclude `.env`/`.env.*`. Multiple driver READMEs instruct contributors to create a `.env` in the home directory for `MQTT_PASSWORD`/`KICKR_MAC_ADDRESS`. No `.env` is currently tracked, but there's no safety net stopping one from being committed by accident.
   → **Task:** add `.env`, `.env.*`, and `*.pem`/`*.key` patterns to `.gitignore`. *(Fixed in this pass — see below.)*

4. **Default `pi` username for SSH access.** The remote-access guide has users SSH as `pi@<ip>` (the Raspberry Pi OS default account), with password auth implied ("username and password ... in the handover document"). Default usernames + password auth is a common brute-force target if the VPN boundary is ever misconfigured.
   → **Task:** migrate to SSH key-based auth and disable password auth (`PasswordAuthentication no` in `sshd_config`), and/or rename the default account.

5. **No dependency manifest for the Python drivers.** There's no `requirements.txt` at the repo root, so the CI's `Safety` dependency scan step is effectively skipped (`if [ -f "requirements.txt" ]`). Bandit (SAST) still runs, but known-CVE dependency scanning currently isn't covering the driver code at all.
   → **Task:** add a `requirements.txt` (or `pyproject.toml`) pinning driver dependencies (`paho-mqtt`, `gatt`, etc.) so Safety actually has something to scan.

### Low priority / hardening

6. Systemd units in `scripts/*.service` have no sandboxing directives (`NoNewPrivileges=true`, `ProtectSystem=strict`, `PrivateTmp=true`). Low risk given they already run as non-root `pi`, but cheap to add.
7. MQTT topics (`bike/<device_id>/...`) don't appear to have per-topic ACLs documented — worth confirming the broker (HiveMQ Cloud) restricts each device credential to its own topic namespace rather than a shared account with full read/write.

## Summary of what was changed in this pass

- `.gitignore`: added `.env`, `.env.*`, `*.pem`, `*.key` to prevent accidental secret commits.
- `.github/workflows/security-scan.yml`: changed trigger from `pull_request_target` → `pull_request`, trimmed `permissions` to least privilege.

Everything else above is left as an open task (checklist item 4) since it involves either team coordination (node_modules cleanup, requirements.txt ownership) or infrastructure access (Pi SSH hardening) outside this repo.
