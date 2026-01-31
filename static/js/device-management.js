// plant_dashboard/static/js/device-management.js

function initializeDeviceManagement() {
    const scanButton = document.getElementById('scan-button');
    const scanResultsContainer = document.getElementById('scan-results-container');
    const addDeviceModal = new bootstrap.Modal(document.getElementById('addDeviceModal'));
    const saveDeviceButton = document.getElementById('save-device-button');

    // Helper to show alerts
    function showAlert(type, message, targetId) {
        const alertBox = document.getElementById(targetId);
        if (alertBox) {
            alertBox.innerHTML = `
                <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                    ${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            `;
            // Automatically close after 5 seconds if not an error
            if (type !== 'danger') {
                setTimeout(() => {
                    const alertElement = alertBox.querySelector('.alert');
                    if (alertElement) {
                        bootstrap.Alert.getInstance(alertElement)?.close();
                    }
                }, 5000);
            }
        }
    }

    scanButton.addEventListener('click', async () => {
        scanButton.disabled = true;
        scanButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Scanning...`;
        scanResultsContainer.style.display = 'block';
        document.getElementById('scan-results-plant-tbody').innerHTML = '';
        document.getElementById('scan-results-switchbot-tbody').innerHTML = '';
        showAlert('info', 'Scanning for BLE devices for 10 seconds...', 'scan-alert-box');
        try {
            const response = await fetch('/api/ble-scan', { method: 'POST' });
            if (!response.ok) throw new Error(`Server responded with status: ${response.status}`);
            const result = await response.json();
            if (result.success) {
                if (result.devices.length > 0) {
                    showAlert('success', `Found ${result.devices.length} devices.`, 'scan-alert-box');
                    renderScanResults(result.devices);
                } else {
                    showAlert('warning', 'No supported devices found.', 'scan-alert-box');
                }
            } else {
                throw new Error(result.message || 'Scan failed on the server.');
            }
        } catch (error) {
            showAlert('danger', `Error: ${error.message}`, 'scan-alert-box');
        } finally {
            scanButton.disabled = false;
            scanButton.innerHTML = `<i class="bi bi-bluetooth"></i> Start Scan`;
        }
    });

    function renderScanResults(devices) {
        const plantTbody = document.getElementById('scan-results-plant-tbody');
        const switchbotTbody = document.getElementById('scan-results-switchbot-tbody');
        devices.forEach(device => {
            const row = document.createElement('tr');
            const addButton = `<button class="btn btn-sm btn-success btn-add" data-name="${device.name}" data-address="${device.address}" data-type="${device.type}">Add</button>`;
            if (device.type === 'plant_sensor') {
                row.innerHTML = `<td>${device.name}</td><td>${device.address}</td><td>${device.rssi} dBm</td><td>${addButton}</td>`;
                plantTbody.appendChild(row);
            } else if (device.type.startsWith('switchbot_')) {
                const deviceTypeBadge = `<span class="badge bg-info">${device.type.replace('switchbot_', '')}</span>`;
                row.innerHTML = `<td>${device.name}</td><td>${device.address}</td><td>${deviceTypeBadge}</td><td>${device.rssi} dBm</td><td>${addButton}</td>`;
                switchbotTbody.appendChild(row);
            }
        });
    }

    scanResultsContainer.addEventListener('click', (event) => {
        if (event.target.classList.contains('btn-add')) {
            const button = event.target;
            document.getElementById('device-name').value = button.dataset.name;
            document.getElementById('device-mac-address').value = button.dataset.address;
            document.getElementById('device-type').value = button.dataset.type;
            document.getElementById('modal-mac-address').textContent = button.dataset.address;
            document.getElementById('modal-device-type').textContent = button.dataset.type;
            addDeviceModal.show();
        }
    });

    saveDeviceButton.addEventListener('click', async () => {
        const deviceData = {
            device_name: document.getElementById('device-name').value,
            mac_address: document.getElementById('device-mac-address').value,
            device_type: document.getElementById('device-type').value
        };
        if (!deviceData.device_name) {
            alert('Device name is required.');
            return;
        }
        saveDeviceButton.disabled = true;
        saveDeviceButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;
        try {
            const response = await fetch('/api/add-device', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(deviceData)
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.message || `Server error: ${response.status}`);
            }
            addDeviceModal.hide();
            showAlert('success', `Device "${deviceData.device_name}" added successfully! Page will reload.`, 'main-alert-box');
            setTimeout(() => window.location.reload(), 2000);
        } catch (error) {
            showAlert('danger', `Error: ${error.message}`, 'main-alert-box');
        } finally {
            saveDeviceButton.disabled = false;
            saveDeviceButton.innerHTML = `Save Device`;
        }
    });

    // LED Control Logic
    document.querySelectorAll('.control-led-button').forEach(button => {
        button.addEventListener('click', async (event) => {
            event.preventDefault();
            event.stopPropagation(); // Prevent the parent <a> tag from being triggered

            const deviceId = button.dataset.deviceId;
            const colorSelect = document.querySelector(`.led-color-select[data-device-id="${deviceId}"]`);
            const brightnessInput = document.querySelector(`.led-brightness-input[data-device-id="${deviceId}"]`);
            const durationInput = document.querySelector(`.led-duration-input[data-device-id="${deviceId}"]`);

            const hexColor = colorSelect.value;
            const brightness = parseInt(brightnessInput.value, 10);
            const duration_ms = parseInt(durationInput.value, 10);

            if (isNaN(brightness) || brightness < 0 || brightness > 100) {
                showAlert('danger', 'Brightness must be between 0 and 100.', 'profiles-alert-box');
                return;
            }
            if (isNaN(duration_ms) || duration_ms < 0) {
                showAlert('danger', 'Duration (ms) must be a non-negative number.', 'profiles-alert-box');
                return;
            }

            const rgb = hexToRgb(hexColor);
            if (!rgb) {
                showAlert('danger', 'Invalid color selected.', 'profiles-alert-box');
                return;
            }

            button.disabled = true;
            button.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Sending...`;

            try {
                const response = await fetch('/api/control-led', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        device_id: deviceId,
                        red: rgb.r,
                        green: rgb.g,
                        blue: rgb.b,
                        brightness: brightness,
                        duration_ms: duration_ms
                    })
                });

                const result = await response.json();
                if (result.success) {
                    showAlert('success', `LED command sent to ${deviceId}!`, 'profiles-alert-box');
                } else {
                    showAlert('danger', `Failed to send LED command to ${deviceId}: ${result.message || 'Unknown error'}`, 'profiles-alert-box');
                }
            } catch (error) {
                showAlert('danger', `Error sending LED command to ${deviceId}: ${error.message}`, 'profiles-alert-box');
            } finally {
                button.disabled = false;
                button.innerHTML = `<i class="bi bi-lightbulb"></i> Light Up`;
            }
        });
    });

    function hexToRgb(hex) {
        let r = 0, g = 0, b = 0;
        // 3 digits
        if (hex.length === 3) {
            r = parseInt(hex[0] + hex[0], 16);
            g = parseInt(hex[1] + hex[1], 16);
            b = parseInt(hex[2] + hex[2], 16);
        } else if (hex.length === 6) { // 6 digits
            r = parseInt(hex.substring(0, 2), 16);
            g = parseInt(hex.substring(2, 4), 16);
            b = parseInt(hex.substring(4, 6), 16);
        }
        return { r, g, b };
    }
}
