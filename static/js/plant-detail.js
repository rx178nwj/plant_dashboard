// plant_dashboard/static/js/plant-detail.js

/**
 * Renders the monthly native climate chart.
 * @param {HTMLElement} canvas The canvas element for the chart.
 */
function renderMonthlyClimateChart(canvas) {
    if (!canvas) return;

    // 既存チャートがあれば破棄
    const existingChart = Chart.getChart(canvas);
    if (existingChart) existingChart.destroy();

    const tempsDataString = canvas.dataset.monthlyTemps;
    if (!tempsDataString || tempsDataString === 'null') {
        console.log("No monthly climate data to render.");
        return;
    }

    try {
        // Jinja's tojson filter on a string results in a double-encoded string
        const temps = JSON.parse(JSON.parse(tempsDataString)); 
        
        if (!temps || typeof temps !== 'object') {
            throw new Error("Parsed climate data is not a valid object.");
        }
        
        const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
        const labels = months.map(m => m.charAt(0).toUpperCase() + m.slice(1));

        const datasets = [{
            label: 'High (°C)',
            data: months.map(m => temps[m]?.high ?? null),
            borderColor: 'rgba(255, 99, 132, 1)',
            backgroundColor: 'rgba(255, 99, 132, 0.2)',
            tension: 0.1,
            fill: false,
        }, {
            label: 'Avg (°C)',
            data: months.map(m => temps[m]?.avg ?? null),
            borderColor: 'rgba(54, 162, 235, 1)',
            backgroundColor: 'rgba(54, 162, 235, 0.2)',
            tension: 0.1,
            fill: false,
            borderWidth: 3,
        }, {
            label: 'Low (°C)',
            data: months.map(m => temps[m]?.low ?? null),
            borderColor: 'rgba(75, 192, 192, 1)',
            backgroundColor: 'rgba(75, 192, 192, 0.2)',
            tension: 0.1,
            fill: false,
        }];

        new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { 
                    title: { display: false },
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } }
                },
                scales: { 
                    y: { 
                        title: { display: true, text: '°C' } 
                    } 
                }
            }
        });

    } catch (e) {
        console.error("Failed to parse or render monthly climate chart:", e);
        const ctx = canvas.getContext('2d');
        ctx.textAlign = 'center';
        ctx.fillStyle = '#6c757d';
        ctx.fillText('Could not load climate data.', canvas.width / 2, canvas.height / 2);
    }
}


/**
 * Initializes all charts on the detail pages (plant and device).
 */
function initializeDetailCharts() {
    const pageContainer = document.getElementById('plant-detail-page') || document.getElementById('device-detail-page');
    if (!pageContainer) return;

    const isPlantDetailPage = (pageContainer.id === 'plant-detail-page');
    const sensorChartInstances = {};
    
    let initialDate = new Date().toISOString().split('T')[0];
    if (isPlantDetailPage && pageContainer.dataset.selectedDate) {
        initialDate = pageContainer.dataset.selectedDate;
    }

    // --- Analysis Chart (Plant Detail Page Only) ---
    if (isPlantDetailPage) {
        const managedPlantId = pageContainer.dataset.plantId;
        const analysisChartInstances = {};
        const analysisChartCanvas = document.getElementById(`analysis-history-chart-${managedPlantId}`);
        if (analysisChartCanvas) {
            const analysisDatePicker = document.getElementById(`analysis-date-picker-${managedPlantId}`);
            if (analysisDatePicker) {
                analysisDatePicker.value = initialDate;
            }

            const analysisFitBtn = pageContainer.querySelector(`.analysis-temp-fit-btn[data-plant-id="${managedPlantId}"]`);
            const analysisTempMinInput = pageContainer.querySelector(`.analysis-temp-min[data-plant-id="${managedPlantId}"]`);
            const analysisTempMaxInput = pageContainer.querySelector(`.analysis-temp-max[data-plant-id="${managedPlantId}"]`);

            const applyAnalysisTempRange = (chart, minVal, maxVal) => {
                if (!chart || !chart.options.scales.y_temp) return;
                chart.options.scales.y_temp.min = minVal;
                chart.options.scales.y_temp.max = maxVal;
                chart.update('none');
            };

            const resetAnalysisFit = () => {
                if (analysisFitBtn) {
                    analysisFitBtn.classList.remove('active');
                    analysisFitBtn.classList.replace('btn-info', 'btn-outline-info');
                }
                if (analysisTempMinInput) analysisTempMinInput.value = '';
                if (analysisTempMaxInput) analysisTempMaxInput.value = '';
            };

            const updateChartFromAnalysisControls = () => {
                const selectedPeriodButton = pageContainer.querySelector(`.analysis-period-btn[data-plant-id="${managedPlantId}"].active`);
                if (!selectedPeriodButton) return;
                const selectedPeriod = selectedPeriodButton.dataset.period;
                const selectedDate = analysisDatePicker ? analysisDatePicker.value : initialDate;
                updateAnalysisHistoryChart(managedPlantId, selectedPeriod, analysisChartInstances, selectedDate);
                resetAnalysisFit();
            };

            updateAnalysisHistoryChart(managedPlantId, '7d', analysisChartInstances, initialDate);

            pageContainer.querySelectorAll('.analysis-period-btn').forEach(button => {
                button.addEventListener('click', (e) => {
                    const { plantId } = e.target.dataset;
                    pageContainer.querySelectorAll(`.analysis-period-btn[data-plant-id="${plantId}"]`).forEach(btn => btn.classList.remove('active'));
                    e.target.classList.add('active');
                    updateChartFromAnalysisControls();
                });
            });

            if (analysisDatePicker) {
                analysisDatePicker.addEventListener('change', updateChartFromAnalysisControls);
            }
            
            const analysisOptionsContainer = document.getElementById(`analysis-chart-options-${managedPlantId}`);
            if (analysisOptionsContainer) {
                analysisOptionsContainer.addEventListener('change', (e) => {
                    if (e.target.matches('input[type="checkbox"]')) {
                        const chart = analysisChartInstances[managedPlantId];
                        if (chart) {
                            const labelToToggle = e.target.dataset.datasetLabel;
                            
                            let datasetsToToggle = {
                                'Temp Range': ['Daily Temp Max', 'Daily Temp Min', 'Daily Temp Avg'],
                                'Humidity Range': ['Daily Humidity Max', 'Daily Humidity Min', 'Avg Humidity (%)'],
                                'Light Range': ['Daily Light Max', 'Daily Light Min', 'Avg Light (lux)'],
                                'Fast Growth Range': ['Fast Growth Range Lower', 'Fast Growth Range Upper'],
                                'Slow Growth Range': ['Slow Growth Range Lower', 'Slow Growth Range Upper'],
                                'Hot Dormancy Range': ['Hot Dormancy Range Lower', 'Hot Dormancy Range Upper'],
                                'Cold Dormancy Range': ['Cold Dormancy Range Lower', 'Cold Dormancy Range Upper'],
                            }[labelToToggle] || [];

                            chart.data.datasets.forEach(dataset => {
                                if (datasetsToToggle.includes(dataset.label)) {
                                    dataset.hidden = !e.target.checked;
                                }
                            });
                            chart.update();
                        }
                    }
                });
            }

            // Fitボタン: 温度軸をデータ範囲 ±5°C に調整
            if (analysisFitBtn) {
                analysisFitBtn.addEventListener('click', () => {
                    const chart = analysisChartInstances[managedPlantId];
                    if (!chart) return;

                    const isFitted = analysisFitBtn.classList.contains('active');

                    if (isFitted) {
                        resetAnalysisFit();
                        applyAnalysisTempRange(chart, undefined, undefined);
                    } else {
                        const tempDataLabels = [
                            'Daily Temp Avg', 'Daily Temp Min', 'Daily Temp Max',
                            'Avg Soil Temp1 (°C)', 'Daily Soil Temp1 Min', 'Daily Soil Temp1 Max',
                            'Avg Soil Temp2 (°C)', 'Daily Soil Temp2 Min', 'Daily Soil Temp2 Max'
                        ];
                        let tempMin = Infinity;
                        let tempMax = -Infinity;
                        chart.data.datasets.forEach(ds => {
                            if (ds.yAxisID === 'y_temp' && ds.data && tempDataLabels.includes(ds.label)) {
                                ds.data.forEach(val => {
                                    if (val !== null && val !== undefined && isFinite(val)) {
                                        if (val < tempMin) tempMin = val;
                                        if (val > tempMax) tempMax = val;
                                    }
                                });
                            }
                        });

                        if (isFinite(tempMin) && isFinite(tempMax)) {
                            const calcMin = Math.floor(tempMin - 5);
                            const calcMax = Math.ceil(tempMax + 5);
                            if (analysisTempMinInput) analysisTempMinInput.value = calcMin;
                            if (analysisTempMaxInput) analysisTempMaxInput.value = calcMax;
                            analysisFitBtn.classList.add('active');
                            analysisFitBtn.classList.replace('btn-outline-info', 'btn-info');
                            applyAnalysisTempRange(chart, calcMin, calcMax);
                        }
                    }
                });
            }

            // Min/Max入力: 手動で温度範囲を設定
            const onAnalysisTempRangeInput = () => {
                const chart = analysisChartInstances[managedPlantId];
                if (!chart) return;

                const minVal = analysisTempMinInput && analysisTempMinInput.value !== '' ? Number(analysisTempMinInput.value) : undefined;
                const maxVal = analysisTempMaxInput && analysisTempMaxInput.value !== '' ? Number(analysisTempMaxInput.value) : undefined;

                if (minVal === undefined && maxVal === undefined) {
                    if (analysisFitBtn) {
                        analysisFitBtn.classList.remove('active');
                        analysisFitBtn.classList.replace('btn-info', 'btn-outline-info');
                    }
                }

                applyAnalysisTempRange(chart, minVal, maxVal);
            };

            if (analysisTempMinInput) analysisTempMinInput.addEventListener('change', onAnalysisTempRangeInput);
            if (analysisTempMaxInput) analysisTempMaxInput.addEventListener('change', onAnalysisTempRangeInput);
        }
    }

    // --- Sensor History Chart (Both Pages) ---
    const sensorChartCanvas = pageContainer.querySelector('canvas[id^="history-chart-"]');
    if (sensorChartCanvas) {
        const deviceId = sensorChartCanvas.id.replace('history-chart-', '');
        const datePicker = document.getElementById(`sensor-date-picker-${deviceId}`);
        
        if (datePicker) {
            datePicker.value = initialDate;
        }
        
        updateSensorHistoryChart(deviceId, '24h', sensorChartInstances, initialDate);

        const updateChartFromSensorControls = () => {
            const selectedPeriodButton = pageContainer.querySelector(`.period-btn[data-device-id="${deviceId}"].active`);
            if (!selectedPeriodButton) return;
            const selectedPeriod = selectedPeriodButton.dataset.period;
            const selectedDate = datePicker ? datePicker.value : new Date().toISOString().split('T')[0];
            updateSensorHistoryChart(deviceId, selectedPeriod, sensorChartInstances, selectedDate);
            // Fitモードと温度範囲入力をリセット
            const fitBtnReset = pageContainer.querySelector(`.sensor-temp-fit-btn[data-device-id="${deviceId}"]`);
            if (fitBtnReset) {
                fitBtnReset.classList.remove('active');
                fitBtnReset.classList.replace('btn-info', 'btn-outline-info');
            }
            const tempMinReset = pageContainer.querySelector(`.sensor-temp-min[data-device-id="${deviceId}"]`);
            const tempMaxReset = pageContainer.querySelector(`.sensor-temp-max[data-device-id="${deviceId}"]`);
            if (tempMinReset) tempMinReset.value = '';
            if (tempMaxReset) tempMaxReset.value = '';
        };

        pageContainer.querySelectorAll(`.period-btn[data-device-id="${deviceId}"]`).forEach(button => {
            button.addEventListener('click', (e) => {
                pageContainer.querySelectorAll(`.period-btn[data-device-id="${deviceId}"]`).forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                updateChartFromSensorControls();
            });
        });

        if (datePicker) {
            datePicker.addEventListener('change', updateChartFromSensorControls);
        }

        // 温度範囲コントロール: Fitボタン + Min/Max入力
        const fitBtn = pageContainer.querySelector(`.sensor-temp-fit-btn[data-device-id="${deviceId}"]`);
        const tempMinInput = pageContainer.querySelector(`.sensor-temp-min[data-device-id="${deviceId}"]`);
        const tempMaxInput = pageContainer.querySelector(`.sensor-temp-max[data-device-id="${deviceId}"]`);

        const applyTempRange = (chart, minVal, maxVal) => {
            if (!chart || !chart.options.scales.y_temp) return;
            chart.options.scales.y_temp.min = minVal;
            chart.options.scales.y_temp.max = maxVal;
            chart.update('none');
        };

        if (fitBtn) {
            fitBtn.addEventListener('click', () => {
                const chart = sensorChartInstances[deviceId];
                if (!chart) return;

                const isFitted = fitBtn.classList.contains('active');

                if (isFitted) {
                    // 自動スケールに戻す
                    if (tempMinInput) tempMinInput.value = '';
                    if (tempMaxInput) tempMaxInput.value = '';
                    fitBtn.classList.remove('active');
                    fitBtn.classList.replace('btn-info', 'btn-outline-info');
                    applyTempRange(chart, undefined, undefined);
                } else {
                    // センサーデータのみから最大/最小を計算
                    const tempDataLabels = [
                        'Temperature (°C)', 'Temp Min', 'Temp Max',
                        'Soil Temp1 (°C)', 'Soil Temp1 Min', 'Soil Temp1 Max',
                        'Soil Temp2 (°C)', 'Soil Temp2 Min', 'Soil Temp2 Max'
                    ];
                    let tempMin = Infinity;
                    let tempMax = -Infinity;
                    chart.data.datasets.forEach(ds => {
                        if (ds.yAxisID === 'y_temp' && ds.data && tempDataLabels.includes(ds.label)) {
                            ds.data.forEach(val => {
                                if (val !== null && val !== undefined && isFinite(val)) {
                                    if (val < tempMin) tempMin = val;
                                    if (val > tempMax) tempMax = val;
                                }
                            });
                        }
                    });

                    if (isFinite(tempMin) && isFinite(tempMax)) {
                        const calcMin = Math.floor(tempMin - 5);
                        const calcMax = Math.ceil(tempMax + 5);
                        if (tempMinInput) tempMinInput.value = calcMin;
                        if (tempMaxInput) tempMaxInput.value = calcMax;
                        fitBtn.classList.add('active');
                        fitBtn.classList.replace('btn-outline-info', 'btn-info');
                        applyTempRange(chart, calcMin, calcMax);
                    }
                }
            });
        }

        // Min/Max入力: 手動で温度範囲を設定
        const onTempRangeInput = () => {
            const chart = sensorChartInstances[deviceId];
            if (!chart) return;

            const minVal = tempMinInput && tempMinInput.value !== '' ? Number(tempMinInput.value) : undefined;
            const maxVal = tempMaxInput && tempMaxInput.value !== '' ? Number(tempMaxInput.value) : undefined;

            // 両方空なら自動スケール、Fitボタンもリセット
            if (minVal === undefined && maxVal === undefined) {
                if (fitBtn) {
                    fitBtn.classList.remove('active');
                    fitBtn.classList.replace('btn-info', 'btn-outline-info');
                }
            }

            applyTempRange(chart, minVal, maxVal);
        };

        if (tempMinInput) tempMinInput.addEventListener('change', onTempRangeInput);
        if (tempMaxInput) tempMaxInput.addEventListener('change', onTempRangeInput);
    }

    // --- Native Climate Chart (Plant Detail Page Only) ---
    if (isPlantDetailPage) {
        const climateChartCanvas = document.getElementById('monthly-climate-chart');
        renderMonthlyClimateChart(climateChartCanvas);
    }
}

// initializeDetailCharts is called from main.js


/**
 * Renders the daily aggregate data chart (`daily_plant_analysis`).
 */
async function updateAnalysisHistoryChart(managedPlantId, period, chartInstances, selectedDate) {
    const canvas = document.getElementById(`analysis-history-chart-${managedPlantId}`);
    const loader = document.getElementById(`analysis-chart-loader-${managedPlantId}`);
    const optionsContainer = document.getElementById(`analysis-chart-options-${managedPlantId}`);
    if (!canvas || !loader) return;
    
    if (chartInstances[managedPlantId]) {
        chartInstances[managedPlantId].destroy();
        delete chartInstances[managedPlantId];
    }
    // 安全策: Chart.getChartでも破棄
    const existingAnalysisChart = Chart.getChart(canvas);
    if (existingAnalysisChart) existingAnalysisChart.destroy();

    loader.classList.remove('d-none');
    canvas.style.visibility = 'hidden';
    if (optionsContainer) optionsContainer.style.display = 'none';

    try {
        const response = await fetch(`/api/plant-analysis-history/${managedPlantId}?period=${period}&date=${selectedDate}`);
        if (!response.ok) throw new Error(`API request failed`);
        
        const responseData = await response.json();
        const historyData = responseData.history;
        const thresholds = responseData.thresholds;

        if (optionsContainer) {
            if (thresholds && Object.keys(thresholds).length > 0) {
                optionsContainer.style.display = 'flex';
            } else {
                optionsContainer.style.display = 'none';
            }
        }

        if (!historyData || historyData.length === 0) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.textAlign = 'center';
            ctx.fillStyle = '#6c757d';
            ctx.fillText('No analysis data available for this period.', canvas.width / 2, canvas.height / 2);
            return;
        }

        const labels = historyData.map(d => new Date(d.analysis_date));
        
        let datasets = [];

        const periodColors = {
            fast_growth: 'rgba(40, 167, 69, 0.15)',
            slow_growth: 'rgba(25, 135, 84, 0.15)',
            hot_dormancy: 'rgba(255, 193, 7, 0.15)',
            cold_dormancy: 'rgba(13, 202, 240, 0.15)'
        };
        
        const addRangeBand = (low, high, label, color, yAxisID) => {
            if (low !== null && high !== null) {
                datasets.push({
                    label: `${label} Lower`, data: Array(labels.length).fill(low),
                    yAxisID: yAxisID, borderColor: 'transparent', backgroundColor: color, pointRadius: 0, fill: '+1'
                }, {
                    label: `${label} Upper`, data: Array(labels.length).fill(high),
                    yAxisID: yAxisID, pointRadius: 0, fill: false, borderColor: 'transparent'
                });
            }
        };

        addRangeBand(thresholds.growing_fast_temp_low, thresholds.growing_fast_temp_high, 'Fast Growth Range', periodColors.fast_growth, 'y_temp');
        addRangeBand(thresholds.growing_slow_temp_low, thresholds.growing_slow_temp_high, 'Slow Growth Range', periodColors.slow_growth, 'y_temp');
        addRangeBand(thresholds.hot_dormancy_temp_low, thresholds.hot_dormancy_temp_high, 'Hot Dormancy Range', periodColors.hot_dormancy, 'y_temp');
        addRangeBand(thresholds.cold_dormancy_temp_low, thresholds.cold_dormancy_temp_high, 'Cold Dormancy Range', periodColors.cold_dormancy, 'y_temp');
        
        if (thresholds && thresholds.lethal_temp_high !== null) {
            datasets.push({
                label: 'Lethal High', data: Array(labels.length).fill(thresholds.lethal_temp_high),
                yAxisID: 'y_temp', borderColor: 'rgba(220, 53, 69, 0.8)', borderWidth: 2, borderDash: [5, 5], pointRadius: 0, fill: false
            });
        }
        if (thresholds && thresholds.lethal_temp_low !== null) {
             datasets.push({
                label: 'Lethal Low', data: Array(labels.length).fill(thresholds.lethal_temp_low),
                yAxisID: 'y_temp', borderColor: 'rgba(13, 110, 253, 0.8)', borderWidth: 2, borderDash: [5, 5], pointRadius: 0, fill: false
            });
        }

        // --- Temperature Datasets ---
        datasets.push({
            label: 'Daily Temp Min', data: historyData.map(d => d.daily_temp_min), yAxisID: 'y_temp',
            borderColor: 'transparent', backgroundColor: 'rgba(220, 53, 69, 0.2)', pointRadius: 0, fill: '+1' 
        });
        datasets.push({
            label: 'Daily Temp Max', data: historyData.map(d => d.daily_temp_max), yAxisID: 'y_temp',
            borderColor: 'transparent', backgroundColor: 'rgba(220, 53, 69, 0.2)', pointRadius: 0, fill: false
        });
        datasets.push({
            label: 'Daily Temp Avg', data: historyData.map(d => d.daily_temp_ave),
            borderColor: 'rgba(220, 53, 69, 1)', yAxisID: 'y_temp', tension: 0.1, borderWidth: 2, pointRadius: 0
        });

        const scales = {
            x: { type: 'time', time: { unit: 'day', tooltipFormat: 'yyyy/MM/dd' } },
            y_temp: { position: 'left', title: { display: true, text: 'Temperature (°C)' } }
        };
        
        // --- Humidity Datasets and Scale ---
        if (historyData.some(d => d.daily_humidity_ave !== null)) {
            datasets.push({
                label: 'Daily Humidity Min', data: historyData.map(d => d.daily_humidity_min), yAxisID: 'y_humid',
                borderColor: 'transparent', backgroundColor: 'rgba(13, 202, 240, 0.2)', pointRadius: 0, fill: '+1'
            });
            datasets.push({
                label: 'Daily Humidity Max', data: historyData.map(d => d.daily_humidity_max), yAxisID: 'y_humid',
                borderColor: 'transparent', backgroundColor: 'rgba(13, 202, 240, 0.2)', pointRadius: 0, fill: false
            });
            datasets.push({
                label: 'Avg Humidity (%)', data: historyData.map(d => d.daily_humidity_ave),
                borderColor: 'rgba(13, 202, 240, 1)', yAxisID: 'y_humid', tension: 0.1, borderWidth: 2, pointRadius: 0
            });
            scales.y_humid = { position: 'right', title: { display: true, text: 'Humidity (%)' }, grid: { drawOnChartArea: false } };
        }
        
        // --- Light Datasets and Scale ---
        if (historyData.some(d => d.daily_light_ave !== null)) {
             datasets.push({
                label: 'Daily Light Min', data: historyData.map(d => d.daily_light_min), yAxisID: 'y_light',
                borderColor: 'transparent', backgroundColor: 'rgba(255, 193, 7, 0.2)', pointRadius: 0, fill: '+1'
            });
             datasets.push({
                label: 'Daily Light Max', data: historyData.map(d => d.daily_light_max), yAxisID: 'y_light',
                borderColor: 'transparent', backgroundColor: 'rgba(255, 193, 7, 0.2)', pointRadius: 0, fill: false
            });
             datasets.push({
                label: 'Avg Light (lux)', data: historyData.map(d => d.daily_light_ave),
                borderColor: 'rgba(255, 193, 7, 1)', yAxisID: 'y_light', tension: 0.1, borderWidth: 2, pointRadius: 0
            });
            scales.y_light = { position: 'right', title: { display: true, text: 'Light (lux)' }, grid: { drawOnChartArea: false } };
        }

        if (historyData.some(d => d.daily_soil_moisture_ave !== null)) {
             datasets.push({
                label: 'Avg Soil Moisture', data: historyData.map(d => d.daily_soil_moisture_ave),
                borderColor: 'rgba(108, 78, 56, 1)', yAxisID: 'y_soil', tension: 0.1, pointRadius: 0
            });
            scales.y_soil = { position: 'right', title: { display: true, text: 'Soil Moisture' }, grid: { drawOnChartArea: false } };
        }

        // --- Soil Temperature 1 Datasets ---
        if (historyData.some(d => d.daily_soil_temp1_ave !== null)) {
            datasets.push({
                label: 'Daily Soil Temp1 Min', data: historyData.map(d => d.daily_soil_temp1_min), yAxisID: 'y_temp',
                borderColor: 'transparent', backgroundColor: 'rgba(0, 150, 136, 0.2)', pointRadius: 0, fill: '+1'
            });
            datasets.push({
                label: 'Daily Soil Temp1 Max', data: historyData.map(d => d.daily_soil_temp1_max), yAxisID: 'y_temp',
                borderColor: 'transparent', backgroundColor: 'rgba(0, 150, 136, 0.2)', pointRadius: 0, fill: false
            });
            datasets.push({
                label: 'Avg Soil Temp1 (°C)', data: historyData.map(d => d.daily_soil_temp1_ave),
                borderColor: 'rgba(0, 150, 136, 1)', yAxisID: 'y_temp', tension: 0.1, borderWidth: 2, pointRadius: 0
            });
        }

        // --- Soil Temperature 2 Datasets ---
        if (historyData.some(d => d.daily_soil_temp2_ave !== null)) {
            datasets.push({
                label: 'Daily Soil Temp2 Min', data: historyData.map(d => d.daily_soil_temp2_min), yAxisID: 'y_temp',
                borderColor: 'transparent', backgroundColor: 'rgba(156, 39, 176, 0.2)', pointRadius: 0, fill: '+1'
            });
            datasets.push({
                label: 'Daily Soil Temp2 Max', data: historyData.map(d => d.daily_soil_temp2_max), yAxisID: 'y_temp',
                borderColor: 'transparent', backgroundColor: 'rgba(156, 39, 176, 0.2)', pointRadius: 0, fill: false
            });
            datasets.push({
                label: 'Avg Soil Temp2 (°C)', data: historyData.map(d => d.daily_soil_temp2_ave),
                borderColor: 'rgba(156, 39, 176, 1)', yAxisID: 'y_temp', tension: 0.1, borderWidth: 2, pointRadius: 0
            });
        }

        if (optionsContainer) {
            optionsContainer.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                const labelToToggle = checkbox.dataset.datasetLabel;
                const datasetsToToggle = {
                    'Temp Range': ['Daily Temp Max', 'Daily Temp Min', 'Daily Temp Avg'],
                    'Humidity Range': ['Daily Humidity Max', 'Daily Humidity Min', 'Avg Humidity (%)'],
                    'Light Range': ['Daily Light Max', 'Daily Light Min', 'Avg Light (lux)'],
                    'Fast Growth Range': ['Fast Growth Range Lower', 'Fast Growth Range Upper'],
                    'Slow Growth Range': ['Slow Growth Range Lower', 'Slow Growth Range Upper'],
                    'Hot Dormancy Range': ['Hot Dormancy Range Lower', 'Hot Dormancy Range Upper'],
                    'Cold Dormancy Range': ['Cold Dormancy Range Lower', 'Cold Dormancy Range Upper'],
                }[labelToToggle] || [];
                
                datasets.forEach(dataset => {
                    if (datasetsToToggle.includes(dataset.label)) {
                        dataset.hidden = !checkbox.checked;
                    }
                });
            });
        }

        chartInstances[managedPlantId] = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true, maintainAspectRatio: false, scales: scales,
                plugins: { 
                    legend: { 
                        labels: { 
                            filter: item => item.text && !item.text.includes('Lower') && !item.text.includes('Upper') && !item.text.includes('Min') && !item.text.includes('Max')
                        } 
                    } 
                }
            }
        });

    } catch (error) {
        console.error(`Analysis chart update error:`, error);
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.textAlign = 'center'; ctx.fillStyle = '#dc3545';
        ctx.fillText('Failed to load analysis data.', canvas.width / 2, canvas.height / 2);
    } finally {
        loader.classList.add('d-none');
        canvas.style.visibility = 'visible';
    }
}


/**
 * Renders the raw sensor history chart (`sensor_data`).
 */
async function updateSensorHistoryChart(deviceId, period, chartInstances, selectedDate) {
    const canvas = document.getElementById(`history-chart-${deviceId}`);
    const loader = document.getElementById(`chart-loader-${deviceId}`);
    const optionsContainer = document.getElementById(`chart-options-${deviceId}`);
    if (!canvas || !loader) return;

    if (chartInstances[deviceId]) {
        chartInstances[deviceId].destroy();
        delete chartInstances[deviceId];
    }
    // 安全策: Chart.getChartでも破棄
    const existingSensorChart = Chart.getChart(canvas);
    if (existingSensorChart) existingSensorChart.destroy();

    loader.classList.remove('d-none');
    canvas.style.visibility = 'hidden';
    if(optionsContainer) optionsContainer.style.display = 'none';

    try {
        const response = await fetch(`/api/history/${deviceId}?period=${period}&date=${selectedDate}`);
        if (!response.ok) throw new Error(`API request failed`);
        
        const responseData = await response.json();
        const historyData = responseData.history;
        const thresholds = responseData.thresholds;
        
        if(optionsContainer){
            if (thresholds && Object.keys(thresholds).length > 0) {
                optionsContainer.style.display = 'flex';
            } else {
                optionsContainer.style.display = 'none';
            }
        }

        if (!historyData || historyData.length === 0) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.textAlign = 'center'; ctx.fillStyle = '#6c757d';
            ctx.fillText('No sensor data available for this period.', canvas.width / 2, canvas.height / 2);
            return;
        }

        const labels = historyData.map(d => new Date(d.timestamp));
        let timeUnit = (period === '7d' || period === '30d') ? 'day' : (period === '1y' ? 'month' : 'hour');

        const datasets = [];
        const isAggregated = historyData[0] && historyData[0].temperature_max !== undefined;

        const periodColors = {
            fast_growth: 'rgba(40, 167, 69, 0.15)',
            slow_growth: 'rgba(25, 135, 84, 0.15)',
            hot_dormancy: 'rgba(255, 193, 7, 0.15)',
            cold_dormancy: 'rgba(13, 202, 240, 0.15)'
        };

        const addRangeBand = (low, high, label, color) => {
            if (thresholds && low !== null && high !== null) {
                datasets.push({
                    label: `${label} Lower`, data: Array(labels.length).fill(low),
                    yAxisID: 'y_temp', borderColor: 'transparent', backgroundColor: color, pointRadius: 0, fill: '+1'
                }, {
                    label: `${label} Upper`, data: Array(labels.length).fill(high),
                    yAxisID: 'y_temp', pointRadius: 0, fill: false, borderColor: 'transparent'
                });
            }
        };

        addRangeBand(thresholds.growing_fast_temp_low, thresholds.growing_fast_temp_high, 'Fast Growth Range', periodColors.fast_growth);
        addRangeBand(thresholds.growing_slow_temp_low, thresholds.growing_slow_temp_high, 'Slow Growth Range', periodColors.slow_growth);
        addRangeBand(thresholds.hot_dormancy_temp_low, thresholds.hot_dormancy_temp_high, 'Hot Dormancy Range', periodColors.hot_dormancy);
        addRangeBand(thresholds.cold_dormancy_temp_low, thresholds.cold_dormancy_temp_high, 'Cold Dormancy Range', periodColors.cold_dormancy);

        if (thresholds && thresholds.lethal_temp_high !== null) {
            datasets.push({
                label: 'Lethal High Temp', data: Array(labels.length).fill(thresholds.lethal_temp_high),
                yAxisID: 'y_temp', borderColor: 'rgba(220, 53, 69, 0.8)', borderWidth: 2, borderDash: [5, 5], pointRadius: 0, fill: false
            });
        }
        if (thresholds && thresholds.lethal_temp_low !== null) {
             datasets.push({
                label: 'Lethal Low Temp', data: Array(labels.length).fill(thresholds.lethal_temp_low),
                yAxisID: 'y_temp', borderColor: 'rgba(13, 110, 253, 0.8)', borderWidth: 2, borderDash: [5, 5], pointRadius: 0, fill: false
            });
        }
        
        const scales = {
            x: { type: 'time', time: { unit: timeUnit, tooltipFormat: 'yyyy/MM/dd HH:mm' } },
            y_temp: { position: 'left', title: { display: true, text: 'Temperature (°C)' } },
            y_humid: { position: 'right', title: { display: true, text: 'Humidity (%)' }, grid: { drawOnChartArea: false } }
        };

        if (isAggregated) {
            // Aggregated data view (min/max bands and average line)
            datasets.push(
                { label: 'Temp Min', data: historyData.map(d => d.temperature_min), yAxisID: 'y_temp', borderColor: 'transparent', backgroundColor: 'rgba(220, 53, 69, 0.2)', pointRadius: 0, fill: '+1' },
                { label: 'Temp Max', data: historyData.map(d => d.temperature_max), yAxisID: 'y_temp', borderColor: 'transparent', backgroundColor: 'rgba(220, 53, 69, 0.2)', pointRadius: 0, fill: false },
                { label: 'Temperature (°C)', data: historyData.map(d => d.temperature), borderColor: 'rgba(220, 53, 69, 1)', yAxisID: 'y_temp', tension: 0.1, borderWidth: 2, pointRadius: 0 },
                { label: 'Humidity Min', data: historyData.map(d => d.humidity_min), yAxisID: 'y_humid', borderColor: 'transparent', backgroundColor: 'rgba(13, 110, 253, 0.2)', pointRadius: 0, fill: '+1' },
                { label: 'Humidity Max', data: historyData.map(d => d.humidity_max), yAxisID: 'y_humid', borderColor: 'transparent', backgroundColor: 'rgba(13, 110, 253, 0.2)', pointRadius: 0, fill: false },
                { label: 'Humidity (%)', data: historyData.map(d => d.humidity), borderColor: 'rgba(13, 110, 253, 1)', yAxisID: 'y_humid', tension: 0.1, borderWidth: 2, pointRadius: 0 }
            );

            if (historyData.some(d => d.light_lux_max !== null)) {
                datasets.push(
                    { label: 'Light Min', data: historyData.map(d => d.light_lux_min), yAxisID: 'y_light', borderColor: 'transparent', backgroundColor: 'rgba(255, 206, 86, 0.2)', pointRadius: 0, fill: '+1' },
                    { label: 'Light Max', data: historyData.map(d => d.light_lux_max), yAxisID: 'y_light', borderColor: 'transparent', backgroundColor: 'rgba(255, 206, 86, 0.2)', pointRadius: 0, fill: false },
                    { label: 'Light (lux)', data: historyData.map(d => d.light_lux), borderColor: 'rgba(255, 206, 86, 1)', yAxisID: 'y_light', tension: 0.1, borderWidth: 2, pointRadius: 0 }
                );
                scales.y_light = { position: 'right', title: { display: true, text: 'Light (lux)' }, grid: { drawOnChartArea: false }};
            }
            if (historyData.some(d => d.soil_moisture_max !== null)) {
                datasets.push(
                    { label: 'Soil Min', data: historyData.map(d => d.soil_moisture_min), yAxisID: 'y_soil', borderColor: 'transparent', backgroundColor: 'rgba(139, 69, 19, 0.2)', pointRadius: 0, fill: '+1' },
                    { label: 'Soil Max', data: historyData.map(d => d.soil_moisture_max), yAxisID: 'y_soil', borderColor: 'transparent', backgroundColor: 'rgba(139, 69, 19, 0.2)', pointRadius: 0, fill: false },
                    { label: 'Soil Moisture', data: historyData.map(d => d.soil_moisture), borderColor: 'rgba(139, 69, 19, 1)', yAxisID: 'y_soil', tension: 0.1, borderWidth: 2, pointRadius: 0 }
                );
                scales.y_soil = { position: 'right', title: { display: true, text: 'Soil Moisture' }, grid: { drawOnChartArea: false } };
            }
            if (historyData.some(d => d.soil_temperature1 !== null)) {
                datasets.push(
                    { label: 'Soil Temp1 Min', data: historyData.map(d => d.soil_temperature1_min), yAxisID: 'y_temp', borderColor: 'transparent', backgroundColor: 'rgba(0, 150, 136, 0.2)', pointRadius: 0, fill: '+1' },
                    { label: 'Soil Temp1 Max', data: historyData.map(d => d.soil_temperature1_max), yAxisID: 'y_temp', borderColor: 'transparent', backgroundColor: 'rgba(0, 150, 136, 0.2)', pointRadius: 0, fill: false },
                    { label: 'Soil Temp1 (°C)', data: historyData.map(d => d.soil_temperature1), borderColor: 'rgba(0, 150, 136, 1)', yAxisID: 'y_temp', tension: 0.1, borderWidth: 2, pointRadius: 0 }
                );
            }
            if (historyData.some(d => d.soil_temperature2 !== null)) {
                datasets.push(
                    { label: 'Soil Temp2 Min', data: historyData.map(d => d.soil_temperature2_min), yAxisID: 'y_temp', borderColor: 'transparent', backgroundColor: 'rgba(156, 39, 176, 0.2)', pointRadius: 0, fill: '+1' },
                    { label: 'Soil Temp2 Max', data: historyData.map(d => d.soil_temperature2_max), yAxisID: 'y_temp', borderColor: 'transparent', backgroundColor: 'rgba(156, 39, 176, 0.2)', pointRadius: 0, fill: false },
                    { label: 'Soil Temp2 (°C)', data: historyData.map(d => d.soil_temperature2), borderColor: 'rgba(156, 39, 176, 1)', yAxisID: 'y_temp', tension: 0.1, borderWidth: 2, pointRadius: 0 }
                );
            }

        } else {
            // Raw data view (24h)
            datasets.push(
                { label: 'Temperature (°C)', data: historyData.map(d => d.temperature), borderColor: 'rgba(220, 53, 69, 0.8)', yAxisID: 'y_temp', tension: 0.2, pointRadius: 0 },
                { label: 'Humidity (%)', data: historyData.map(d => d.humidity), borderColor: 'rgba(13, 110, 253, 0.8)', yAxisID: 'y_humid', tension: 0.2, pointRadius: 0 }
            );

            if (historyData.some(d => d.light_lux !== null)) {
                datasets.push(
                    { label: 'Light (lux)', data: historyData.map(d => d.light_lux), borderColor: 'rgba(255, 206, 86, 0.8)', yAxisID: 'y_light', tension: 0.2, pointRadius: 0 }
                );
                scales.y_light = { position: 'right', title: { display: true, text: 'Light (lux)' }, grid: { drawOnChartArea: false }};
            }
            if (historyData.some(d => d.soil_moisture !== null)) {
                datasets.push(
                    { label: 'Soil Moisture', data: historyData.map(d => d.soil_moisture), borderColor: 'rgba(139, 69, 19, 0.8)', yAxisID: 'y_soil', tension: 0.2, pointRadius: 0 }
                );
                scales.y_soil = { position: 'right', title: { display: true, text: 'Soil Moisture' }, grid: { drawOnChartArea: false } };
            }
            if (historyData.some(d => d.soil_temperature1 !== null)) {
                datasets.push(
                    { label: 'Soil Temp1 (°C)', data: historyData.map(d => d.soil_temperature1), borderColor: 'rgba(0, 150, 136, 0.8)', yAxisID: 'y_temp', tension: 0.2, pointRadius: 0 }
                );
            }
            if (historyData.some(d => d.soil_temperature2 !== null)) {
                datasets.push(
                    { label: 'Soil Temp2 (°C)', data: historyData.map(d => d.soil_temperature2), borderColor: 'rgba(156, 39, 176, 0.8)', yAxisID: 'y_temp', tension: 0.2, pointRadius: 0 }
                );
            }
        }
        
        chartInstances[deviceId] = new Chart(canvas.getContext('2d'), {
            type: 'line', data: { labels: labels, datasets: datasets },
            options: {
                responsive: true, maintainAspectRatio: false, scales: scales,
                plugins: {
                    legend: { 
                        labels: { 
                            filter: item => item.text && !item.text.includes('Range') && !item.text.includes('Temp') && !item.text.includes('Min') && !item.text.includes('Max') 
                        } 
                    },
                    tooltip: { 
                        callbacks: { 
                            filter: item => item.dataset.label && !item.dataset.label.includes('Range') && !item.dataset.label.includes('Temp') && !item.dataset.label.includes('Min') && !item.dataset.label.includes('Max')
                        } 
                    }
                }
            }
        });
        
        if(optionsContainer){
            const newOptionsContainer = optionsContainer.cloneNode(true);
            optionsContainer.parentNode.replaceChild(newOptionsContainer, optionsContainer);
            newOptionsContainer.style.display = 'flex';

            newOptionsContainer.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                 checkbox.addEventListener('change', (e) => {
                    const chart = chartInstances[deviceId];
                    if (chart) {
                        const labelToToggle = e.target.dataset.datasetLabel;
                        chart.data.datasets.forEach(dataset => {
                            if (dataset.label.startsWith(labelToToggle)) {
                                dataset.hidden = !e.target.checked;
                            }
                        });
                        chart.update();
                    }
                });
            });
        }

    } catch (error) {
        console.error(`Sensor chart update error for ${deviceId}:`, error);
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.textAlign = 'center'; ctx.fillStyle = '#dc3545';
        ctx.fillText('Failed to load sensor data.', canvas.width / 2, canvas.height / 2);
    } finally {
        loader.classList.add('d-none');
        canvas.style.visibility = 'visible';
    }
}