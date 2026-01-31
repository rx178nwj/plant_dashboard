// static/js/device-detail.js

document.addEventListener('DOMContentLoaded', function() {
    initializeDeviceDetailPage();
});

function initializeDeviceDetailPage() {
    const pageContainer = document.getElementById('device-detail-page');
    if (!pageContainer) {
        return;
    }

    const deviceId = pageContainer.dataset.deviceId;
    const chartInstances = {};

    // Initial chart load
    let selectedDate = new Date().toISOString().split('T')[0];
    updateHistoryChart(deviceId, '24h', chartInstances, selectedDate);

    // Event listeners for period buttons
    pageContainer.querySelectorAll('.period-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const period = e.target.dataset.period;
            pageContainer.querySelectorAll(`.period-btn[data-device-id="${deviceId}"]`).forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            updateHistoryChart(deviceId, period, chartInstances, selectedDate);
        });
    });

    // Event listener for date picker
    const datePicker = document.getElementById(`sensor-date-picker-${deviceId}`);
    if (datePicker) {
        datePicker.value = selectedDate;
        datePicker.addEventListener('change', (e) => {
            selectedDate = e.target.value;
            const activePeriodButton = pageContainer.querySelector('.period-btn.active');
            const period = activePeriodButton ? activePeriodButton.dataset.period : '24h';
            updateHistoryChart(deviceId, period, chartInstances, selectedDate);
        });
    }

    // LED Control Logic
    const controlLedButton = document.getElementById('control-led-button');
    if (controlLedButton) {
        controlLedButton.addEventListener('click', async () => {
            const colorSelect = document.getElementById('led-color-select');
            const brightnessInput = document.getElementById('led-brightness-input');
            const durationInput = document.getElementById('led-duration-input');

            const hexColor = colorSelect.value;
            const brightness = parseInt(brightnessInput.value, 10);
            const duration_ms = parseInt(durationInput.value, 10);
            const rgb = hexToRgb(hexColor);

            if (!rgb) {
                showAlert('danger', 'Invalid color format.', 'device-detail-alert-box');
                return;
            }

            controlLedButton.disabled = true;
            controlLedButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Sending...`;

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
                    showAlert('success', 'LED control command sent successfully.', 'device-detail-alert-box');
                } else {
                    throw new Error(result.message || 'Failed to send command.');
                }
            } catch (error) {
                showAlert('danger', `Error: ${error.message}`, 'device-detail-alert-box');
            } finally {
                controlLedButton.disabled = false;
                controlLedButton.innerHTML = `<i class="bi bi-lightbulb-fill"></i> Light Up`;
            }
        });
    }
}

function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

async function updateHistoryChart(deviceId, period, chartInstances, selectedDate) {
    const canvas = document.getElementById(`history-chart-${deviceId}`);
    const loader = document.getElementById(`chart-loader-${deviceId}`);
    if (!canvas || !loader) {
        console.error('Chart canvas or loader not found for device:', deviceId);
        return;
    }

    const ctx = canvas.getContext('2d');
    if (chartInstances[deviceId]) {
        chartInstances[deviceId].destroy();
    }

    loader.classList.remove('d-none');
    canvas.style.display = 'none';

    try {
        const response = await fetch(`/api/history/${deviceId}?period=${period}&date=${selectedDate}`);
        if (!response.ok) {
            throw new Error(`API request failed with status ${response.status}`);
        }
        
        const responseData = await response.json();
        const historyData = responseData.history;

        if (!historyData || historyData.length === 0) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.textAlign = 'center';
            ctx.fillStyle = '#6c757d';
            ctx.fillText('No data available for this period.', canvas.width / 2, canvas.height / 2);
            return;
        }

        const labels = historyData.map(d => new Date(d.timestamp));
        let timeUnit = 'hour';
        if (period === '7d' || period === '30d') {
            timeUnit = 'day';
        } else if (period === '1y') {
            timeUnit = 'month';
        }
        
        const datasets = [];
        const scales = {
            x: {
                type: 'time',
                time: { 
                    unit: timeUnit,
                    tooltipFormat: 'yyyy/MM/dd HH:mm'
                },
            }
        };

        // Standard datasets
        if (historyData[0].temperature !== undefined) {
            datasets.push({
                label: 'Temperature (°C)',
                data: historyData.map(d => ({x: new Date(d.timestamp), y: d.temperature})),
                borderColor: '#DC3545', // Red
                yAxisID: 'y_temp',
                tension: 0.2,
                pointRadius: 0,
                fill: false,
            });
            scales.y_temp = { position: 'left', title: { display: true, text: 'Temperature (°C)' } };
        }
        if (historyData[0].humidity !== undefined) {
            datasets.push({
                label: 'Humidity (%)',
                data: historyData.map(d => ({x: new Date(d.timestamp), y: d.humidity})),
                borderColor: '#0D6EFD', // Blue
                yAxisID: 'y_humid',
                tension: 0.2,
                pointRadius: 0,
                fill: false,
            });
            scales.y_humid = { position: 'right', title: { display: true, text: 'Humidity (%)' }, grid: { drawOnChartArea: false } };
        }
        if (historyData[0].light_lux !== undefined) {
            datasets.push({
                label: 'Light (lux)',
                data: historyData.map(d => ({x: new Date(d.timestamp), y: d.light_lux})),
                borderColor: '#FFC107', // Yellow
                yAxisID: 'y_light',
                tension: 0.2,
                pointRadius: 0,
                fill: false,
            });
            scales.y_light = { position: 'right', title: { display: true, text: 'Light (lux)' }, grid: { drawOnChartArea: false } };
        }

        // Add extended data if available (data_version >= 2)
        if (historyData[0].capacitance_ch1 !== undefined) {
            const capacitanceColors = ['#28A745', '#20C997', '#17A2B8', '#00BCD4']; // Greenish/Cyan colors
            for (let i = 1; i <= 4; i++) {
                datasets.push({
                    label: `Soil Moisture CH${i} (pF)`,
                    data: historyData.map(d => ({x: new Date(d.timestamp), y: d[`capacitance_ch${i}`]})),
                    borderColor: capacitanceColors[i-1],
                    yAxisID: 'y_soil_pf',
                    tension: 0.2,
                    pointRadius: 0,
                    fill: false,
                });
            }
            scales.y_soil_pf = { position: 'right', title: { display: true, text: 'Soil Moisture (pF)' }, grid: { drawOnChartArea: false } };
        } else if (historyData[0].soil_moisture !== undefined) {
            datasets.push({
                label: 'Soil Moisture (Raw)',
                data: historyData.map(d => ({x: new Date(d.timestamp), y: d.soil_moisture})),
                borderColor: '#28a745',
                yAxisID: 'y_soil_raw',
                tension: 0.2,
                pointRadius: 0,
                fill: false,
            });
            scales.y_soil_raw = { position: 'right', title: { display: true, text: 'Soil Moisture (Raw)' }, grid: { drawOnChartArea: false } };
        }

        if (historyData[0].soil_temperature1 !== undefined) {
            const soilTempColors = ['#6F42C1', '#D63384', '#FD7E14', '#FFC107']; // Purple, Pink, Orange, Yellow
            for (let i = 1; i <= 4; i++) {
                if (historyData[0][`soil_temperature${i}`] !== undefined) {
                    datasets.push({
                        label: `Soil Temp ${i} (°C)`,
                        data: historyData.map(d => ({x: new Date(d.timestamp), y: d[`soil_temperature${i}`]})),
                        borderColor: soilTempColors[i-1],
                        yAxisID: 'y_temp',
                        tension: 0.2,
                        pointRadius: 0,
                        fill: false,
                    });
                }
            }
        }
        
        chartInstances[deviceId] = new Chart(ctx, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: scales,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                },
                interaction: {
                    mode: 'index',
                    intersect: false
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
        canvas.style.display = 'block';
    }
}
