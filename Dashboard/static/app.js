let ws = null; 
let currentGrade = 0.0; 
let currentResistance = 35;
let currentFanSpeed = 0;
let currentDeviceId = "000001";
let mqttMessageCount = 0; 
let mqttBuffer = [];

const history = { 
  speed: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
  cadence: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
  power: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 
  hr: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] 
};

function connectWebSocket() { 
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"; 
  const wsUrl = `${protocol}//${window.location.host}/ws`; 
  ws = new WebSocket(wsUrl);

  ws.onopen = () => { 
    document.getElementById("badge-mqtt").classList.add("active"); 
    appendDeltaLog({ type: "system", msg: "Connected to Dashboard WebSocket Server." });
  };

  ws.onmessage = (event) => { 
    const data = JSON.parse(event.data);
    if (data.type === "init") {
      if (data.state) updateUI(data.state);
      if (data.mqtt_buffer) {
        data.mqtt_buffer.forEach(addMqttRow);
      }
    } else if (data.type === "telemetry") {
      if (data.state) updateUI(data.state);
      if (data.deltas && data.deltas.length > 0) {
        data.deltas.forEach(appendDeltaLog);
      }
      if (data.mqtt_event) {
        addMqttRow(data.mqtt_event);
      }
    } else if (data.type === "sim_status") {
      isSim = data.active;
      updateSimButton();
    }
  };

  ws.onclose = () => { 
    document.getElementById("badge-mqtt").classList.remove("active"); 
    toggleBadge("badge-kickr", false);
    toggleBadge("badge-climb", false);
    toggleBadge("badge-hr", false);
    toggleBadge("badge-fan", false);
    toggleBadge("badge-btn", false);
    setTimeout(connectWebSocket, 2000); 
  }; 
}

function updateUI(state) { 
  currentDeviceId = state.device_id || "000001";
  
  // Sync Device dropdown
  const devSelect = document.getElementById("device-select");
  if (devSelect) {
    if (currentDeviceId === "000001" || currentDeviceId === "000002") {
      devSelect.value = currentDeviceId;
      document.getElementById("custom-device-id").classList.add("hidden");
    } else {
      devSelect.value = "custom";
      const customInput = document.getElementById("custom-device-id");
      customInput.classList.remove("hidden");
      customInput.value = currentDeviceId;
    }
  }

  // Speed
  const spd = typeof state.speed === "number" ? state.speed : 0.0;
  const spdMs = typeof state.speed_ms === "number" ? state.speed_ms : (spd / 3.6);
  document.getElementById("val-speed").innerText = spd.toFixed(1);
  const msEl = document.getElementById("val-speed-ms");
  if (msEl) msEl.innerText = spdMs.toFixed(2);

  // Cadence, Power, HR
  document.getElementById("val-cadence").innerText = state.cadence || 0; 
  document.getElementById("val-power").innerText = state.power || 0; 
  
  const hr = state.heart_rate || 0;
  document.getElementById("val-hr").innerText = hr > 0 ? hr : "--";
  const hrZoneEl = document.getElementById("val-hr-zone");
  if (hrZoneEl) {
    if (hr === 0) hrZoneEl.innerText = "No Signal";
    else if (hr < 100) hrZoneEl.innerText = "Resting";
    else if (hr < 125) hrZoneEl.innerText = "Fat Burn";
    else if (hr < 150) hrZoneEl.innerText = "Aerobic";
    else if (hr < 175) hrZoneEl.innerText = "Anaerobic";
    else hrZoneEl.innerText = "Max Effort";
  }

  // Resistance
  currentResistance = typeof state.resistance === "number" ? state.resistance : 0;
  const resEl = document.getElementById("val-resistance");
  if (resEl) resEl.innerText = currentResistance;
  const resBar = document.getElementById("bar-resistance");
  if (resBar) resBar.style.width = `${Math.min(100, Math.max(0, currentResistance))}%`;
  const resStageBadge = document.getElementById("badge-resistance-stage");
  if (resStageBadge) {
    resStageBadge.innerText = state.workout_stage && state.workout_stage !== "idle" ? state.workout_stage.toUpperCase() : "Manual";
  }

  // Headwind Fan
  currentFanSpeed = typeof state.fan_speed === "number" ? state.fan_speed : 0;
  const fanEl = document.getElementById("val-fan");
  if (fanEl) fanEl.innerText = currentFanSpeed;
  const fanBar = document.getElementById("bar-fan");
  if (fanBar) fanBar.style.width = `${Math.min(100, Math.max(0, currentFanSpeed))}%`;
  const fanLvlBadge = document.getElementById("badge-fan-level");
  if (fanLvlBadge) {
    const lvl = typeof state.fan_level === "number" ? state.fan_level : Math.round(currentFanSpeed / 20.0);
    fanLvlBadge.innerText = `Level ${lvl}`;
  }

  // Sparklines
  pushSparkline("speed", spd, 50, "#3b82f6"); 
  pushSparkline("cadence", state.cadence || 0, 130, "#8b5cf6"); 
  pushSparkline("power", state.power || 0, 500, "#f59e0b"); 
  pushSparkline("hr", hr, 200, "#f43f5e");

  // Incline Climb Angle
  currentGrade = typeof state.climb_grade === "number" ? state.climb_grade : 0.0; 
  const gradeSign = currentGrade > 0 ? "+" : ""; 
  document.getElementById("val-grade-badge").innerText = `${gradeSign}${currentGrade.toFixed(1)}%`;
  
  const sliderClimb = document.getElementById("slider-climb");
  const sliderClimbVal = document.getElementById("slider-climb-val");
  if (sliderClimb && document.activeElement !== sliderClimb) {
    sliderClimb.value = currentGrade;
  }
  if (sliderClimbVal) {
    sliderClimbVal.innerText = `${gradeSign}${currentGrade.toFixed(1)}%`;
  }

  const angle = Math.max(-15, Math.min(15, currentGrade * 1.5)); 
  document.getElementById("bike-pitch-container").style.transform = `rotate(${-angle}deg)`;

  // Steering
  const steer = state.steering || "CENTER"; 
  document.getElementById("steer-left").className = "steer-node" + (steer === "LEFT" ? " active" : ""); 
  document.getElementById("steer-center").className = "steer-node" + (steer === "CENTER" ? " active" : ""); 
  document.getElementById("steer-right").className = "steer-node" + (steer === "RIGHT" ? " active" : "");

  // Brakes
  const isBraking = state.brake || (state.brake_front > 10 || state.brake_rear > 10); 
  const brakePill = document.getElementById("brake-status-pill"); 
  const fVal = state.brake_front || (state.brake ? 100 : 0); 
  const rVal = state.brake_rear || (state.brake ? 80 : 0);

  if (isBraking) { 
    brakePill.innerText = "ENGAGED"; 
    brakePill.className = "pill-engaged"; 
  } else { 
    brakePill.innerText = "DISENGAGED"; 
    brakePill.className = "pill-inactive"; 
  }

  document.getElementById("bar-brake-front").style.width = `${fVal}%`; 
  document.getElementById("bar-brake-rear").style.width = `${rVal}%`; 
  document.getElementById("val-brake-front").innerText = `${fVal}%`; 
  document.getElementById("val-brake-rear").innerText = `${rVal}%`;

  // Workout Summary
  const workoutPill = document.getElementById("workout-status-pill");
  if (workoutPill) {
    const wName = state.workout_name || "None";
    const wStage = state.workout_stage || "idle";
    if (wStage !== "idle" && wName !== "None") {
      workoutPill.innerText = `ACTIVE: ${wName.toUpperCase()} [${wStage.toUpperCase()}]`;
      workoutPill.style.color = "#10b981";
      workoutPill.style.borderColor = "#10b981";
    } else {
      workoutPill.innerText = "STATUS: IDLE";
      workoutPill.style.color = "var(--accent-blue)";
      workoutPill.style.borderColor = "rgba(59, 130, 246, 0.3)";
    }
  }
  const wStageVal = document.getElementById("val-workout-stage");
  if (wStageVal) wStageVal.innerText = state.workout_stage ? state.workout_stage.toUpperCase() : "--";
  const wPowerVal = document.getElementById("val-workout-target-power");
  if (wPowerVal) wPowerVal.innerText = `${state.target_power || 0} W`;
  const wFtpVal = document.getElementById("val-workout-ftp-pct");
  if (wFtpVal) wFtpVal.innerText = `${(state.ftp_percent || 0).toFixed(1)}% FTP`;

  // Status Badges
  toggleBadge("badge-kickr", state.kickr_connected); 
  toggleBadge("badge-climb", state.climb_connected); 
  toggleBadge("badge-hr", state.heartrate_connected); 
  toggleBadge("badge-fan", state.fan_connected);
  toggleBadge("badge-btn", state.button_connected);
}

function toggleBadge(id, active) { 
  const el = document.getElementById(id); 
  if (!el) return;
  if (active) el.classList.add("active"); 
  else el.classList.remove("active"); 
}

function pushSparkline(key, value, maxVal, color) { 
  if (!history[key]) return;
  history[key].push(value); 
  if (history[key].length > 15) history[key].shift();

  const svg = document.getElementById(`spark-${key}`); 
  if (!svg) return;
  const pts = history[key]; 
  const step = 100 / (pts.length - 1);

  const pointsStr = pts.map((v, i) => { 
    const x = (i * step).toFixed(1); 
    const y = (24 - (Math.min(v, maxVal) / maxVal) * 20).toFixed(1); 
    return `${x},${y}`; 
  }).join(" ");

  svg.innerHTML = `<polyline fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${pointsStr}"/>`; 
}

function appendDeltaLog(delta) { 
  const list = document.getElementById("delta-log-list"); 
  if (!list) return;
  const time = new Date().toLocaleTimeString(); 
  const row = document.createElement("div"); 
  row.className = `log-entry ${delta.type || "system"}`; 
  row.innerHTML = `<span class="log-ts">[${time}]</span> <span class="log-msg">${escapeHtml(delta.msg)}</span>`; 
  list.prepend(row); 
}

function clearLogs() { 
  const list = document.getElementById("delta-log-list");
  if (list) list.innerHTML = ""; 
}

function addMqttRow(item) { 
  mqttMessageCount++; 
  const cnt = document.getElementById("mqtt-counter");
  if (cnt) cnt.innerText = mqttMessageCount; 
  mqttBuffer.unshift(item); 
  if (mqttBuffer.length > 300) mqttBuffer.pop(); 
  renderMqttTable(); 
}

function renderMqttTable() { 
  const tbody = document.getElementById("mqtt-table-body"); 
  if (!tbody) return;
  const filter = document.getElementById("mqtt-filter").value.toLowerCase();

  const rows = mqttBuffer
    .filter(i => !filter || i.topic.toLowerCase().includes(filter) || i.payload.toLowerCase().includes(filter))
    .slice(0, 60)
    .map(i => `<tr>
                 <td style="color:#64748b;">${i.timestamp}</td>
                 <td><span class="topic-badge">${escapeHtml(i.topic)}</span></td>
                 <td>${i.qos}</td>
                 <td>${i.size}B</td>
                 <td><code>${escapeHtml(i.payload)}</code></td>
               </tr>`).join("");
  tbody.innerHTML = rows; 
}

function filterMqttTable() { 
  renderMqttTable(); 
}

function clearMqttTable() { 
  mqttBuffer = []; 
  mqttMessageCount = 0; 
  const cnt = document.getElementById("mqtt-counter");
  if (cnt) cnt.innerText = "0"; 
  renderMqttTable(); 
}

function switchTab(tabId) { 
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active")); 
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

  if (tabId === 'overview') { 
    document.getElementById("tab-btn-overview").classList.add("active"); 
    document.getElementById("tab-overview").classList.add("active"); 
  } else { 
    document.getElementById("tab-btn-mqtt").classList.add("active"); 
    document.getElementById("tab-mqtt").classList.add("active"); 
  } 
}

// Incline Controls
function adjustClimb(deltaOrValue) { 
  let target = deltaOrValue === 0 ? 0.0 : currentGrade + deltaOrValue; 
  target = Math.max(-10, Math.min(19, target)); 
  sendClimbGrade(target);
}

function onClimbSliderInput(val) {
  const grade = parseFloat(val);
  const sign = grade > 0 ? "+" : "";
  const el = document.getElementById("slider-climb-val");
  if (el) el.innerText = `${sign}${grade.toFixed(1)}%`;
}

function sendClimbGrade(val) {
  const target = Math.max(-10, Math.min(19, parseFloat(val)));
  if (ws) ws.send(JSON.stringify({ action: "set_incline", grade: target })); 
}

// Resistance Controls
function onResistanceSliderInput(val) {
  const el = document.getElementById("resistance-control-label");
  if (el) el.innerText = `${val}%`;
}

function sendResistance(val) {
  const target = Math.max(0, Math.min(100, parseInt(val)));
  const slider = document.getElementById("slider-resistance");
  if (slider) slider.value = target;
  onResistanceSliderInput(target);
  if (ws) ws.send(JSON.stringify({ action: "set_resistance", resistance: target }));
}

// Fan Controls
function sendFanLevel(lvl) {
  const targetLvl = Math.max(0, Math.min(5, parseInt(lvl)));
  const label = document.getElementById("fan-control-label");
  if (label) label.innerText = targetLvl === 0 ? "Off (0%)" : `Level ${targetLvl} (${targetLvl * 20}%)`;
  if (ws) ws.send(JSON.stringify({ action: "set_fan", level: targetLvl }));
}

// Workout Controls
function startSelectedWorkout() {
  const select = document.getElementById("workout-type-select");
  const ftpInput = document.getElementById("workout-ftp-input");
  const workoutName = select ? select.value : "Endurance";
  const ftp = ftpInput ? parseFloat(ftpInput.value) : 200;
  if (ws) {
    ws.send(JSON.stringify({
      action: "set_workout",
      workout: workoutName,
      ftp: ftp,
      workout_action: "start"
    }));
  }
}

function stopWorkout() {
  if (ws) {
    ws.send(JSON.stringify({
      action: "set_workout",
      workout_action: "stop"
    }));
  }
}

// Device Switcher
function onDeviceSelectChange() {
  const sel = document.getElementById("device-select");
  const custom = document.getElementById("custom-device-id");
  if (sel.value === "custom") {
    custom.classList.remove("hidden");
    custom.focus();
  } else {
    custom.classList.add("hidden");
    switchDevice(sel.value);
  }
}

function onCustomDeviceSubmit() {
  const custom = document.getElementById("custom-device-id");
  if (custom && custom.value.trim()) {
    switchDevice(custom.value.trim());
  }
}

function switchDevice(deviceId) {
  if (ws) {
    ws.send(JSON.stringify({
      action: "switch_device",
      device_id: deviceId
    }));
  }
}

// MQTT Publisher Tool
function applyPublishTemplate(templateName) {
  const topicInput = document.getElementById("pub-topic-input");
  const payloadInput = document.getElementById("pub-payload-input");
  if (!templateName) return;

  const ts = Math.floor(Date.now() / 1000);
  if (templateName === "incline") {
    topicInput.value = `bike/${currentDeviceId}/incline/control`;
    payloadInput.value = JSON.stringify({ incline: 5.0, timestamp: ts }, null, 2);
  } else if (templateName === "resistance") {
    topicInput.value = `bike/${currentDeviceId}/resistance/control`;
    payloadInput.value = JSON.stringify({ resistance: 45, target_power_watts: 180, ftp_percent: 75.0, stage: "active", timestamp: ts }, null, 2);
  } else if (templateName === "fan") {
    topicInput.value = `bike/${currentDeviceId}/fan/control`;
    payloadInput.value = JSON.stringify({ level: 3, value: 60, timestamp: ts }, null, 2);
  } else if (templateName === "btn_left") {
    topicInput.value = `bike/${currentDeviceId}/button/report`;
    payloadInput.value = JSON.stringify({ button: "LEFT", state: 1, timestamp: ts }, null, 2);
  } else if (templateName === "btn_brake") {
    topicInput.value = `bike/${currentDeviceId}/button/report`;
    payloadInput.value = JSON.stringify({ button: "BREAK", state: 1, timestamp: ts }, null, 2);
  }
}

function publishCustomMqtt() {
  const topic = document.getElementById("pub-topic-input").value.trim();
  const payload = document.getElementById("pub-payload-input").value.trim();
  const qos = parseInt(document.getElementById("pub-qos-select").value);

  if (!topic) {
    alert("Please specify a topic.");
    return;
  }

  if (ws) {
    ws.send(JSON.stringify({
      action: "publish_mqtt",
      topic: topic,
      payload: payload,
      qos: qos
    }));
    appendDeltaLog({ type: "system", msg: `Published custom message to ${topic}` });
  }
}

function escapeHtml(str) { 
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); 
}

window.addEventListener("DOMContentLoaded", () => {
  connectWebSocket();
  const pubTopic = document.getElementById("pub-topic-input");
  if (pubTopic) pubTopic.value = `bike/${currentDeviceId}/resistance/control`;
});

