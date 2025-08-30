// plant_dashboard/static/js/main.js

document.addEventListener('DOMContentLoaded', function() {
    // ページ上の要素の存在を確認して、対応する初期化関数を呼び出す
    if (document.getElementById('dashboard-page')) initializeDashboard();
    if (document.getElementById('scan-button')) initializeDeviceManagement();
    if (document.getElementById('plant-list')) initializePlantLibrary();
    if (document.getElementById('managed-plant-list')) initializeManagementDashboard();
});


// --- Dashboard Functions ---
function initializeDashboard() {
    const pageContainer = document.getElementById('dashboard-page');
    const selectedDate = pageContainer.dataset.selectedDate;
    const isToday = pageContainer.dataset.isToday === 'True';
    const chartInstances = {};

    const datePicker = document.getElementById('dashboard-date-picker');
    if (datePicker) {
        datePicker.addEventListener('change', (e) => {
            window.location.href = `/?date=${e.target.value}`;
        });
    }

    const chartCanvases = document.querySelectorAll('canvas[id^="history-chart-"]');
    chartCanvases.forEach(canvas => {
        const deviceId = canvas.id.replace('history-chart-', '');
        updateHistoryChart(deviceId, '24h', chartInstances, selectedDate);
    });

    document.querySelectorAll('.period-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const { deviceId, period } = e.target.dataset;
            document.querySelectorAll(`.period-btn[data-device-id="${deviceId}"]`).forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            updateHistoryChart(deviceId, period, chartInstances, selectedDate);
        });
    });

    if (isToday) {
        const eventSource = new EventSource("/stream");
        eventSource.onmessage = function(event) {
            const devices = JSON.parse(event.data);
            updateDeviceCards(devices);
        };
    }
}

async function updateHistoryChart(deviceId, period, chartInstances, selectedDate) {
    const canvas = document.getElementById(`history-chart-${deviceId}`);
    const loader = document.getElementById(`chart-loader-${deviceId}`);
    if (!canvas || !loader) return;

    const ctx = canvas.getContext('2d');
    if (chartInstances[deviceId]) {
        chartInstances[deviceId].destroy();
    }

    loader.classList.remove('d-none');
    canvas.style.visibility = 'hidden';

    try {
        const response = await fetch(`/api/history/${deviceId}?period=${period}&date=${selectedDate}`);
        if (!response.ok) throw new Error(`API request failed`);
        
        const historyData = await response.json();
        if (historyData.length === 0) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.textAlign = 'center';
            ctx.fillStyle = '#6c757d';
            ctx.fillText('No data available for this period.', canvas.width / 2, canvas.height / 2);
            return;
        }

        const labels = historyData.map(d => new Date(d.timestamp));
        let timeUnit = 'hour';
        if (period === '7d' || period === '30d') timeUnit = 'day';
        else if (period === '1y') timeUnit = 'month';

        chartInstances[deviceId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Temperature (°C)',
                        data: historyData.map(d => d.temperature),
                        borderColor: 'rgba(220, 53, 69, 0.8)',
                        yAxisID: 'y_temp',
                        tension: 0.2,
                    },
                    {
                        label: 'Humidity (%)',
                        data: historyData.map(d => d.humidity),
                        borderColor: 'rgba(13, 110, 253, 0.8)',
                        yAxisID: 'y_humid',
                        tension: 0.2,
                    }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: timeUnit, tooltipFormat: 'yyyy/MM/dd HH:mm' },
                    },
                    y_temp: { position: 'left', title: { display: true, text: 'Temperature (°C)' } },
                    y_humid: { position: 'right', title: { display: true, text: 'Humidity (%)' }, grid: { drawOnChartArea: false } }
                }
            }
        });
    } catch (error) {
        console.error(`Chart update error for ${deviceId}:`, error);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.textAlign = 'center';
        ctx.fillStyle = '#dc3545';
        ctx.fillText('Failed to load chart data.', canvas.width / 2, canvas.height / 2);
    } finally {
        loader.classList.add('d-none');
        canvas.style.visibility = 'visible';
    }
}

function updateDeviceCards(devices) {
    devices.forEach(device => {
        updateElementText(`temp-${device.device_id}`, device.last_data.temperature?.toFixed(1) || '--');
        updateElementText(`humidity-${device.device_id}`, device.last_data.humidity?.toFixed(1) || '--');
        updateElementText(`light-${device.device_id}`, device.last_data.light_lux || '--');
        updateElementText(`soil-${device.device_id}`, device.last_data.soil_moisture || '--');
        updateElementText(`battery-${device.device_id}`, device.battery_level || '--');
        updateStatusVisuals(device.device_id, device.connection_status);
    });
}

function updateElementText(id, text) {
    const element = document.getElementById(id);
    if (element && element.textContent !== text) {
        element.textContent = text;
    }
}

function updateStatusVisuals(deviceId, status) {
    const card = document.getElementById(`device-card-${deviceId}`);
    const iconElement = document.getElementById(`status-icon-${deviceId}`);
    if (!card || !iconElement) return;

    card.className = card.className.replace(/\bstatus-\S+/g, '');
    card.classList.add(`status-${status}`);

    let iconHtml = '<i class="bi bi-question-circle"></i>';
    switch (status) {
        case 'connected': case 'historical': iconHtml = '<i class="bi bi-check-circle-fill"></i>'; break;
        case 'disconnected': iconHtml = '<i class="bi bi-x-circle-fill"></i>'; break;
        case 'error': iconHtml = '<i class="bi bi-exclamation-triangle-fill"></i>'; break;
        case 'no_data': iconHtml = '<i class="bi bi-archive-fill"></i>'; break;
    }
    iconElement.innerHTML = iconHtml;
}

// --- Device Management Functions ---
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
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.message || `Server error: ${response.status}`);
            }
            addDeviceModal.hide();
            showAlert('success', `Device "${deviceData.device_name}" added successfully! Page will reload.`, 'scan-alert-box');
            setTimeout(() => window.location.reload(), 2000);
        } catch (error) {
            alert(`Error: ${error.message}`);
        } finally {
            saveDeviceButton.disabled = false;
            saveDeviceButton.innerHTML = `Save Device`;
        }
    });
}

// --- Plant Library Functions ---
function initializePlantLibrary() {
    const addPlantBtn = document.getElementById('add-plant-btn');
    const aiLookupBtn = document.getElementById('ai-lookup-btn');
    const savePlantBtn = document.getElementById('save-plant-btn');
    const plantList = document.getElementById('plant-list');
    const editorArea = document.getElementById('plant-editor-area');
    const placeholder = document.getElementById('plant-editor-placeholder');
    const plantForm = document.getElementById('plant-form');
    let plantsData = [];

    const loadPlants = async () => {
        try {
            const response = await fetch('/api/plants');
            plantsData = await response.json();
            renderPlantList(plantsData);
        } catch (error) { console.error('Failed to load plants:', error); }
    };

    const renderPlantList = (plants) => {
        if (plants.length === 0) {
            plantList.innerHTML = '<div class="list-group-item">No plants yet.</div>'; return;
        }
        plantList.innerHTML = plants.map(p => `<a href="#" class="list-group-item list-group-item-action" data-plant-id="${p.plant_id}"><strong>${p.variety || p.species}</strong><br><small class="text-muted">${p.genus}</small></a>`).join('');
    };

    addPlantBtn.addEventListener('click', () => {
        plantForm.reset();
        document.getElementById('plant-id').value = '';
        document.getElementById('editor-title').textContent = 'New Plant';
        placeholder.style.display = 'none';
        editorArea.style.display = 'block';
    });

    plantList.addEventListener('click', (e) => {
        e.preventDefault();
        const target = e.target.closest('.list-group-item');
        if (!target) return;
        plantList.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
        target.classList.add('active');
        const plant = plantsData.find(p => p.plant_id === target.dataset.plantId);
        if(plant) {
            populatePlantForm(plant);
            placeholder.style.display = 'none';
            editorArea.style.display = 'block';
        }
    });
    
    savePlantBtn.addEventListener('click', async () => {
        const plantData = {};
        new FormData(plantForm).forEach((value, key) => {
            // This needs to be adapted for complex forms (like monthly temps)
            plantData[key.replace(/-/g, '_')] = value;
        });
        // Manual handling for complex parts might be needed
        try {
            const response = await fetch('/api/plants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(plantData)
            });
            if (!response.ok) { throw new Error('Failed to save plant info.'); }
            loadPlants();
            editorArea.style.display = 'none';
            placeholder.style.display = 'block';
        } catch (error) {
            alert('Error saving plant info.');
        }
    });

    const populatePlantForm = (data) => {
        if (!data) return;
        plantForm.reset();
        for (const key in data) {
            const el = plantForm.querySelector(`#${key.replace(/_/g, '-')}`);
            if (el) {
                el.value = data[key];
            }
        }
    };

    loadPlants();
}

// --- Management Dashboard Functions ---
function initializeManagementDashboard() {
    const addPlantBtn = document.getElementById('add-managed-plant-btn');
    const savePlantBtn = document.getElementById('save-managed-plant-btn');
    const plantList = document.getElementById('managed-plant-list');
    const editorArea = document.getElementById('editor-area');
    const placeholder = document.getElementById('editor-placeholder');
    const managementForm = document.getElementById('management-form');
    let managedPlantsData = [];

    const loadManagedPlants = async () => {
        try {
            const response = await fetch('/api/managed-plants');
            managedPlantsData = await response.json();
            renderManagedPlantList(managedPlantsData);
        } catch (error) { console.error('Failed to load managed plants:', error); }
    };

    const renderManagedPlantList = (plants) => {
        if (plants.length === 0) {
            plantList.innerHTML = '<div class="list-group-item">No plants yet.</div>'; return;
        }
        plantList.innerHTML = plants.map(p => `<a href="#" class="list-group-item list-group-item-action" data-managed-plant-id="${p.managed_plant_id}">${p.plant_name}</a>`).join('');
    };

    addPlantBtn.addEventListener('click', () => {
        managementForm.reset();
        document.getElementById('managed-plant-id').value = '';
        document.getElementById('editor-title').textContent = 'Add New Managed Plant';
        placeholder.style.display = 'none';
        editorArea.style.display = 'block';
    });
    
    plantList.addEventListener('click', (e) => {
        e.preventDefault();
        const target = e.target.closest('.list-group-item');
        if (!target) return;
        plantList.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
        target.classList.add('active');
        const plant = managedPlantsData.find(p => p.managed_plant_id === target.dataset.managedPlantId);
        if(plant) {
            populateManagementForm(plant);
            placeholder.style.display = 'none';
            editorArea.style.display = 'block';
        }
    });

    savePlantBtn.addEventListener('click', async () => {
        const plantData = {
            managed_plant_id: document.getElementById('managed-plant-id').value,
            plant_name: document.getElementById('plant-name').value,
            library_plant_id: document.getElementById('library-plant-id').value,
            assigned_plant_sensor_id: document.getElementById('assigned-plant-sensor-id').value,
            assigned_switchbot_id: document.getElementById('assigned-switchbot-id').value,
        };
        try {
            const response = await fetch('/api/managed-plants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(plantData)
            });
            if (!response.ok) { throw new Error('Failed to save plant.'); }
            loadManagedPlants();
            editorArea.style.display = 'none';
            placeholder.style.display = 'block';
        } catch (error) {
            alert('Error saving plant.');
        }
    });

    const populateManagementForm = (data) => {
        managementForm.reset();
        if (!data) return;
        document.getElementById('managed-plant-id').value = data.managed_plant_id;
        document.getElementById('plant-name').value = data.plant_name;
        document.getElementById('library-plant-id').value = data.library_plant_id;
        document.getElementById('assigned-plant-sensor-id').value = data.assigned_plant_sensor_id;
        document.getElementById('assigned-switchbot-id').value = data.assigned_switchbot_id;
        document.getElementById('editor-title').textContent = `Editing: ${data.plant_name}`;
    };

    loadManagedPlants();
}

function showAlert(type, message, containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = `<div class="alert alert-${type} alert-dismissible fade show" role="alert">${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>`;
    }
}
