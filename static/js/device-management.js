// plant_dashboard/static/js/device-management.js

function initializeDeviceManagement() {
    const scanButton = document.getElementById('scan-button');
    const scanResultsContainer = document.getElementById('scan-results-container');
    const addDeviceModal = new bootstrap.Modal(document.getElementById('addDeviceModal'));
    const saveDeviceButton = document.getElementById('save-device-button');

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
}
