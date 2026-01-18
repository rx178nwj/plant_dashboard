// plant_dashboard/static/js/dashboard.js

/**
 * ダッシュボードページ固有の機能を初期化します。
 * (日付ピッカー、リアルタイム更新)
 */
function initializeDashboard() {
    const pageContainer = document.getElementById('dashboard-page');
    if (!pageContainer) return;

    const isToday = pageContainer.dataset.isToday === 'True';

    // 日付ピッカーのイベントリスナーを設定
    const datePicker = document.getElementById('dashboard-date-picker');
    if (datePicker) {
        datePicker.addEventListener('change', (e) => {
            window.location.href = `/?date=${e.target.value}`;
        });
    }
    
    // 今日の日付が表示されている場合のみ、リアルタイム更新を有効化
    if (isToday) {
        const eventSource = new EventSource("/stream");
        eventSource.onmessage = function(event) {
            const plants = JSON.parse(event.data);
            updatePlantCards(plants);
        };
    }
}


/**
 * ページ上のすべての履歴グラフを初期化します。
 * この関数はダッシュボードページでのみ使用されます。
 */
function initializePageCharts() {
    const pageContainer = document.getElementById('dashboard-page');
    if (!pageContainer) return;

    const chartInstances = {};
    const dateForChart = pageContainer.dataset.selectedDate || new Date().toISOString().split('T')[0];

    const chartCanvases = pageContainer.querySelectorAll('canvas[id^="history-chart-"]');
    chartCanvases.forEach(canvas => {
        const deviceId = canvas.id.replace('history-chart-', '');
        updateHistoryChart(deviceId, '24h', chartInstances, dateForChart);
    });

    pageContainer.querySelectorAll('.period-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const { deviceId, period } = e.target.dataset;
            pageContainer.querySelectorAll(`.period-btn[data-device-id="${deviceId}"]`).forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            updateHistoryChart(deviceId, period, chartInstances, dateForChart);
        });
    });
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
        
        const responseData = await response.json();
        const historyData = responseData.history; 

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

        const datasets = [{
            label: 'Temperature (°C)',
            data: historyData.map(d => d.temperature),
            borderColor: 'rgba(220, 53, 69, 0.8)',
            yAxisID: 'y_temp',
            tension: 0.2,
        }, {
            label: 'Humidity (%)',
            data: historyData.map(d => d.humidity),
            borderColor: 'rgba(13, 110, 253, 0.8)',
            yAxisID: 'y_humid',
            tension: 0.2,
        }];

        const scales = {
            x: {
                type: 'time',
                time: { unit: timeUnit, tooltipFormat: 'yyyy/MM/dd HH:mm' },
            },
            y_temp: { position: 'left', title: { display: true, text: 'Temperature (°C)' } },
            y_humid: { position: 'right', title: { display: true, text: 'Humidity (%)' }, grid: { drawOnChartArea: false } }
        };

        if (historyData.some(d => d.light_lux !== null || d.soil_moisture !== null)) {
            datasets.push({
                label: 'Light (lux)',
                data: historyData.map(d => d.light_lux),
                borderColor: 'rgba(255, 206, 86, 0.8)',
                yAxisID: 'y_light',
                tension: 0.2,
            });
            datasets.push({
                label: 'Soil Moisture',
                data: historyData.map(d => d.soil_moisture),
                borderColor: 'rgba(139, 69, 19, 0.8)',
                yAxisID: 'y_soil',
                tension: 0.2,
            });

            scales.y_light = { 
                position: 'right', 
                title: { display: true, text: 'Light (lux)' }, 
                grid: { drawOnChartArea: false },
                ticks: {
                    callback: function(value) {
                        if (value >= 1000) return (value / 1000) + 'k';
                        return value;
                    }
                }
            };
            scales.y_soil = { 
                position: 'right', 
                title: { display: true, text: 'Soil Moisture' }, 
                grid: { drawOnChartArea: false } 
            };
        }

        chartInstances[deviceId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: scales
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

function updatePlantCards(plants) {
    plants.forEach(plant => {
        const plantId = plant.managed_plant_id;
        const sensorData = plant.sensors?.primary || {};
        const analysis = plant.analysis || {};

        // Update sensor values
        updateElementText(`temp-${plantId}`, sensorData.temperature?.toFixed(1) || '--');
        updateElementText(`humidity-${plantId}`, sensorData.humidity?.toFixed(1) || '--');
        updateElementText(`light-${plantId}`, sensorData.light_lux?.toFixed(1) || '--');
        updateElementText(`soil-${plantId}`, sensorData.soil_moisture?.toFixed(2) || '--');

        // Update soil temperature values if available
        if (sensorData.soil_temperature1 != null) {
            updateElementText(`soil-temp1-${plantId}`, sensorData.soil_temperature1.toFixed(1));
        }
        if (sensorData.soil_temperature2 != null) {
            updateElementText(`soil-temp2-${plantId}`, sensorData.soil_temperature2.toFixed(1));
        }

        // Update analysis icon based on growth period and survival status
        const analysisEl = document.getElementById(`analysis-${plantId}`);
        if (analysisEl) {
            const growth = analysis.growth_period || 'unknown';
            const survival = analysis.survival_limit_status || 'safe';

            const iconMap = {
                'lethal_high': { file: 'LethalHighTemp.svg', title: 'Lethal High Temp', textClass: 'text-danger' },
                'lethal_low': { file: 'LethalLowTemp.svg', title: 'Lethal Low Temp', textClass: 'text-info' },
                'fast_growth': { file: 'FastGrowth.svg', title: 'Fast Growth', textClass: 'text-success' },
                'slow_growth': { file: 'SlowGrowth.svg', title: 'Slow Growth', textClass: 'text-secondary' },
                'hot_dormancy': { file: 'HotDormancy.svg', title: 'Hot Dormancy', textClass: 'text-warning' },
                'cold_dormancy': { file: 'ColdDormancy.svg', title: 'Cold Dormancy', textClass: 'text-primary' }
            };

            let iconInfo = null;
            if (survival === 'lethal_high' || survival === 'lethal_low') {
                iconInfo = iconMap[survival];
            } else if (iconMap[growth]) {
                iconInfo = iconMap[growth];
            }

            if (iconInfo) {
                analysisEl.innerHTML = `<img src="/static/icons/${iconInfo.file}" alt="${iconInfo.title}" title="${iconInfo.title}" style="height: 43px;"><span class="ms-2 small fw-bold ${iconInfo.textClass}">${iconInfo.title}</span>`;
            } else {
                analysisEl.innerHTML = `<span class="badge bg-light text-muted" title="Unknown"><i class="bi bi-question-circle fs-5"></i></span><span class="ms-2 small text-muted">Unknown</span>`;
            }
        }
    });
}


function updateElementText(id, text) {
    const element = document.getElementById(id);
    if (element && element.textContent.trim() !== String(text).trim()) {
        element.textContent = text;
    }
}
