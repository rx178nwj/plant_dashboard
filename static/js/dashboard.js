// plant_dashboard/static/js/dashboard.js

function initializeDashboard() {
    const pageContainer = document.getElementById('dashboard-page');
    if (!pageContainer) return;

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
