// static/js/device-threshold.js

/**
 * Initializes the functionality for the Device Threshold Configuration page.
 */
function initializeDeviceThreshold() {
    const pageContainer = document.getElementById('device-threshold-page');
    if (!pageContainer) return;

    const deviceId = pageContainer.dataset.deviceId;
    const managedPlantId = pageContainer.dataset.managedPlantId;
    const libraryPlantId = pageContainer.dataset.libraryPlantId;

    // If no plant is assigned, there's nothing to configure
    if (!managedPlantId) {
        console.log('No plant assigned to this device. Configuration not available.');
        return;
    }

    // DOM element references
    const saveBtn = document.getElementById('save-profile-btn');
    const writeBtn = document.getElementById('write-profile-btn');
    const alertBox = document.getElementById('device-threshold-alert-box');

    if (!writeBtn || !saveBtn) {
        console.error("Device threshold page is missing one or more key elements.");
        return;
    }

    const dryThresholdInput = document.getElementById('dry-threshold');
    const wetThresholdInput = document.getElementById('wet-threshold');
    const dryThresholdSlider = document.getElementById('dry-threshold-slider');
    const wetThresholdSlider = document.getElementById('wet-threshold-slider');
    const dryValueLabel = document.getElementById('dry-threshold-value');
    const wetValueLabel = document.getElementById('wet-threshold-value');
    const dryVoltageLabel = document.getElementById('dry-threshold-voltage');
    const wetVoltageLabel = document.getElementById('wet-threshold-voltage');

    const wateringDaysFastInput = document.getElementById('watering-days-fast-growth');
    const wateringDaysSlowInput = document.getElementById('watering-days-slow-growth');
    const wateringDaysHotInput = document.getElementById('watering-days-hot-dormancy');
    const wateringDaysColdInput = document.getElementById('watering-days-cold-dormancy');

    const canvas = document.getElementById('soil-history-chart');
    const loader = document.getElementById('chart-loader');
    let chartInstance = null; // To hold the Chart.js instance

    // Synchronization: Slider <-> Input <-> Label (Binary Value: 0-4095)
    // Voltage display is reference only

    // Function to update chart threshold lines
    function updateChartThresholds() {
        if (!chartInstance) return;

        const dryValue = parseInt(dryThresholdInput.value, 10);
        const wetValue = parseInt(wetThresholdInput.value, 10);

        // Update annotations
        const annotations = {};

        if (!isNaN(dryValue) && dryValue >= 0 && dryValue <= 4095) {
            annotations.dryLine = {
                type: 'line', yMin: dryValue, yMax: dryValue,
                borderColor: 'rgb(220, 53, 69, 0.7)', borderWidth: 2, borderDash: [6, 6],
                label: { content: `Dry (${dryValue})`, display: true, position: 'end', color: 'rgb(220, 53, 69, 0.9)', font: {weight: 'bold'} }
            };
        }

        if (!isNaN(wetValue) && wetValue >= 0 && wetValue <= 4095) {
            annotations.wetLine = {
                type: 'line', yMin: wetValue, yMax: wetValue,
                borderColor: 'rgb(13, 110, 253, 0.7)', borderWidth: 2, borderDash: [6, 6],
                label: { content: `Wet (${wetValue})`, display: true, position: 'start', color: 'rgb(13, 110, 253, 0.9)', font: {weight: 'bold'} }
            };
        }

        // Update chart options
        chartInstance.options.plugins.annotation.annotations = annotations;
        chartInstance.update('none'); // Update without animation for smooth real-time update
    }

    // Function to update all elements for dry threshold
    function updateDryThreshold(binaryValue) {
        const voltageValue = (parseFloat(binaryValue) / 1000).toFixed(3);
        dryThresholdSlider.value = binaryValue;
        dryThresholdInput.value = binaryValue;
        dryValueLabel.textContent = binaryValue;
        dryVoltageLabel.textContent = voltageValue;
        updateChartThresholds(); // Update chart in real-time
    }

    // Function to update all elements for wet threshold
    function updateWetThreshold(binaryValue) {
        const voltageValue = (parseFloat(binaryValue) / 1000).toFixed(3);
        wetThresholdSlider.value = binaryValue;
        wetThresholdInput.value = binaryValue;
        wetValueLabel.textContent = binaryValue;
        wetVoltageLabel.textContent = voltageValue;
        updateChartThresholds(); // Update chart in real-time
    }

    // Initialize with default slider values
    updateDryThreshold(dryThresholdSlider.value);
    updateWetThreshold(wetThresholdSlider.value);

    // Update all elements when slider changes
    dryThresholdSlider.addEventListener('input', () => {
        updateDryThreshold(dryThresholdSlider.value);
    });

    wetThresholdSlider.addEventListener('input', () => {
        updateWetThreshold(wetThresholdSlider.value);
    });

    // Update slider and labels when input changes
    dryThresholdInput.addEventListener('input', () => {
        const binaryValue = parseInt(dryThresholdInput.value, 10);
        if (!isNaN(binaryValue) && binaryValue >= 0 && binaryValue <= 4095) {
            updateDryThreshold(binaryValue);
        }
    });

    wetThresholdInput.addEventListener('input', () => {
        const binaryValue = parseInt(wetThresholdInput.value, 10);
        if (!isNaN(binaryValue) && binaryValue >= 0 && binaryValue <= 4095) {
            updateWetThreshold(binaryValue);
        }
    });

    // Load initial data
    (async function() {
        await Promise.all([
            fetchAndDisplayProfile(managedPlantId),
            fetchAndDisplayChart(deviceId, managedPlantId)
        ]);
    })();

    /**
     * Handles the save button click event.
     */
    saveBtn.addEventListener('click', async () => {
        console.log("Save Profile button clicked.");

        // Save binary values (0-4095) directly to DB
        const profileData = {
            soil_moisture_dry_threshold_voltage: parseInt(dryThresholdInput.value, 10) || null,
            soil_moisture_wet_threshold_voltage: parseInt(wetThresholdInput.value, 10) || null,
            watering_days_fast_growth: parseInt(wateringDaysFastInput.value, 10) || null,
            watering_days_slow_growth: parseInt(wateringDaysSlowInput.value, 10) || null,
            watering_days_hot_dormancy: parseInt(wateringDaysHotInput.value, 10) || null,
            watering_days_cold_dormancy: parseInt(wateringDaysColdInput.value, 10) || null,
        };

        saveBtn.disabled = true;
        saveBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;

        try {
            const response = await fetch(`/api/managed-plant-watering-profile/${managedPlantId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(profileData)
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.message || 'Failed to save profile.');
            }
            showAlert(alertBox, 'success', 'Watering profile saved successfully to the database!');

            // Refresh chart with new thresholds
            await fetchAndDisplayChart(deviceId, managedPlantId);
        } catch (error) {
            showAlert(alertBox, 'danger', `Error: ${error.message}`);
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = 'Save Profile to DB';
        }
    });

    /**
     * Handles the write to device button click event.
     */
    writeBtn.addEventListener('click', async () => {
        console.log("Write to Device button clicked.");

        // Send binary values (0-4095) directly to device
        const profileData = {
            dry_threshold: parseInt(dryThresholdInput.value, 10) || 0,
            wet_threshold: parseInt(wetThresholdInput.value, 10) || 0,
        };

        console.log(`Preparing to write to device ${deviceId} with payload:`, profileData);

        writeBtn.disabled = true;
        writeBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Writing...`;

        try {
            const response = await fetch(`/api/device/${deviceId}/write-watering-profile`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(profileData)
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.message || 'Failed to write to device.');
            }
            showAlert(alertBox, 'success', 'Command sent to device successfully!');
        } catch (error) {
            showAlert(alertBox, 'danger', `Error writing to device: ${error.message}`);
        } finally {
            writeBtn.disabled = false;
            writeBtn.innerHTML = '<i class="bi bi-bluetooth"></i> Write to Device';
        }
    });

    /**
     * Fetches and displays the watering profile for the managed plant.
     */
    async function fetchAndDisplayProfile(managedPlantId) {
        try {
            const response = await fetch(`/api/managed-plant-watering-profile/${managedPlantId}`);
            if (!response.ok) throw new Error('Could not fetch profile.');
            const data = await response.json();

            // Set dry threshold - DB stores binary values (0-4095) directly
            const dryBinary = data.soil_moisture_dry_threshold_voltage;
            if (dryBinary !== null && dryBinary !== undefined) {
                updateDryThreshold(Math.round(dryBinary));
            } else {
                // Default values
                updateDryThreshold(2800);
            }

            // Set wet threshold - DB stores binary values (0-4095) directly
            const wetBinary = data.soil_moisture_wet_threshold_voltage;
            if (wetBinary !== null && wetBinary !== undefined) {
                updateWetThreshold(Math.round(wetBinary));
            } else {
                // Default values
                updateWetThreshold(1200);
            }

            wateringDaysFastInput.value = data.watering_days_fast_growth || '';
            wateringDaysSlowInput.value = data.watering_days_slow_growth || '';
            wateringDaysHotInput.value = data.watering_days_hot_dormancy || '';
            wateringDaysColdInput.value = data.watering_days_cold_dormancy || '';

        } catch (error) {
            console.error('Profile fetch error:', error);
            showAlert(alertBox, 'warning', 'Could not load existing profile settings.');
        }
    }

    /**
     * Fetches sensor history and displays it in a chart with threshold lines.
     */
    async function fetchAndDisplayChart(sensorId, managedPlantId) {
        if (chartInstance) {
            chartInstance.destroy();
        }
        loader.classList.remove('d-none');
        canvas.style.visibility = 'hidden';

        try {
            const today = new Date().toISOString().split('T')[0];
            const [historyResponse, profileResponse] = await Promise.all([
                fetch(`/api/history/${sensorId}?period=30d&date=${today}`),
                fetch(`/api/managed-plant-watering-profile/${managedPlantId}`)
            ]);

            if (!historyResponse.ok) throw new Error('Could not fetch sensor history.');
            const historyJson = await historyResponse.json();
            const historyData = historyJson.history;

            const profileData = profileResponse.ok ? await profileResponse.json() : {};

            const ctx = canvas.getContext('2d');
            if (!historyData || historyData.length === 0) {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.textAlign = 'center';
                ctx.fillStyle = '#6c757d';
                ctx.fillText('No soil moisture data available for the last 30 days.', canvas.width / 2, canvas.height / 2);
                return;
            }

            const labels = historyData.map(d => new Date(d.timestamp));
            const soilData = historyData.map(d => d.soil_moisture);

            const annotations = {};

            // Display threshold lines using binary values (0-4095)
            const dryBinary = profileData.soil_moisture_dry_threshold_voltage;
            const wetBinary = profileData.soil_moisture_wet_threshold_voltage;

            if (dryBinary !== null && dryBinary !== undefined) {
                annotations.dryLine = {
                    type: 'line', yMin: dryBinary, yMax: dryBinary,
                    borderColor: 'rgb(220, 53, 69, 0.7)', borderWidth: 2, borderDash: [6, 6],
                    label: { content: `Dry (${dryBinary})`, display: true, position: 'end', color: 'rgb(220, 53, 69, 0.9)', font: {weight: 'bold'} }
                };
            }
            if (wetBinary !== null && wetBinary !== undefined) {
                annotations.wetLine = {
                    type: 'line', yMin: wetBinary, yMax: wetBinary,
                    borderColor: 'rgb(13, 110, 253, 0.7)', borderWidth: 2, borderDash: [6, 6],
                    label: { content: `Wet (${wetBinary})`, display: true, position: 'start', color: 'rgb(13, 110, 253, 0.9)', font: {weight: 'bold'} }
                };
            }

            chartInstance = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Soil Moisture (Binary Value)',
                        data: soilData,
                        borderColor: 'rgb(25, 135, 84)',
                        backgroundColor: 'rgba(25, 135, 84, 0.1)',
                        fill: true,
                        tension: 0.1,
                        pointRadius: 1,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { type: 'time', time: { unit: 'day' } },
                        y: { title: { display: true, text: 'Sensor Value (0-4095)' } }
                    },
                    plugins: {
                        annotation: { annotations: annotations }
                    }
                }
            });
        } catch (error) {
            console.error('Chart display error:', error);
            showAlert(alertBox, 'danger', 'Failed to load chart data.');
        } finally {
            loader.classList.add('d-none');
            canvas.style.visibility = 'visible';
        }
    }
}
