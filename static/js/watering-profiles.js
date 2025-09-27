// static/js/watering-profiles.js

/**
 * Initializes the functionality for the Watering Profiles page.
 */
function initializeWateringProfiles() {
    const pageContainer = document.getElementById('watering-profiles-page');
    if (!pageContainer) return;

    // DOM element references
    const plantList = document.getElementById('plant-list-profiles');
    const editorArea = document.getElementById('editor-area-profiles');
    const placeholder = document.getElementById('editor-placeholder-profiles');
    const editorTitle = document.getElementById('editor-title-profiles');
    const saveBtn = document.getElementById('save-profile-btn');
    const libraryIdInput = document.getElementById('library-plant-id-input'); // This is now only for reference if needed, not for saving

    const dryThresholdInput = document.getElementById('dry-threshold');
    const wetThresholdInput = document.getElementById('wet-threshold');
    const wateringDaysFastInput = document.getElementById('watering-days-fast-growth');
    const wateringDaysSlowInput = document.getElementById('watering-days-slow-growth');
    const wateringDaysHotInput = document.getElementById('watering-days-hot-dormancy');
    const wateringDaysColdInput = document.getElementById('watering-days-cold-dormancy');

    const canvas = document.getElementById('soil-history-chart');
    const loader = document.getElementById('chart-loader-profiles');
    let chartInstance = null; // To hold the Chart.js instance

    /**
     * Handles clicks on the plant list.
     */
    plantList.addEventListener('click', async (e) => {
        e.preventDefault();
        const target = e.target.closest('.list-group-item');
        if (!target) return;

        // Highlight the selected item
        plantList.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
        target.classList.add('active');

        const { managedPlantId, libraryPlantId, sensorId } = target.dataset;
        editorTitle.textContent = `Editing: ${target.textContent.trim()}`;
        
        // We use managedPlantId for fetching and saving profiles now.
        // libraryIdInput.value = libraryPlantId; // No longer the primary ID for this page's logic

        // Show editor and hide placeholder
        placeholder.style.display = 'none';
        editorArea.style.display = 'block';

        // Fetch profile settings and chart data concurrently
        await Promise.all([
            fetchAndDisplayProfile(managedPlantId),
            fetchAndDisplayChart(sensorId, libraryPlantId, managedPlantId) // Pass managedPlantId for profile fetching
        ]);
    });

    /**
     * Handles the save button click event.
     */
    saveBtn.addEventListener('click', async () => {
        const activePlant = plantList.querySelector('.list-group-item.active');
        if (!activePlant) return;

        const { managedPlantId, libraryPlantId, sensorId } = activePlant.dataset;
        if (!managedPlantId) return;

        const profileData = {
            soil_moisture_dry_threshold_voltage: parseFloat(dryThresholdInput.value) || null,
            soil_moisture_wet_threshold_voltage: parseFloat(wetThresholdInput.value) || null,
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
            showAlert('success', 'Watering profile saved successfully!', 'main-alert-box');
            
            // Re-render chart with new threshold lines
            if(activePlant) {
                fetchAndDisplayChart(sensorId, libraryPlantId, managedPlantId);
            }
        } catch (error) {
            showAlert('danger', `Error: ${error.message}`, 'main-alert-box');
        } finally {
            saveBtn.disabled = false;
            saveBtn.innerHTML = 'Save Profile';
        }
    });
    
    /**
     * Fetches and populates the watering profile settings form.
     * @param {string} managedPlantId - The ID of the managed plant profile to fetch.
     */
    async function fetchAndDisplayProfile(managedPlantId) {
        try {
            const response = await fetch(`/api/managed-plant-watering-profile/${managedPlantId}`);
            if (!response.ok) throw new Error('Could not fetch profile.');
            const data = await response.json();

            dryThresholdInput.value = data.soil_moisture_dry_threshold_voltage || '';
            wetThresholdInput.value = data.soil_moisture_wet_threshold_voltage || '';
            wateringDaysFastInput.value = data.watering_days_fast_growth || '';
            wateringDaysSlowInput.value = data.watering_days_slow_growth || '';
            wateringDaysHotInput.value = data.watering_days_hot_dormancy || '';
            wateringDaysColdInput.value = data.watering_days_cold_dormancy || '';

        } catch (error) {
            console.error('Profile fetch error:', error);
            showAlert('warning', 'Could not load existing profile settings.', 'main-alert-box');
        }
    }

    /**
     * Fetches historical sensor data and renders the chart.
     * @param {string} sensorId - The device ID of the sensor.
     * @param {string} libraryPlantId - The plant library ID (can be used for other things if needed).
     * @param {string} managedPlantId - The managed plant ID to fetch thresholds for.
     */
    async function fetchAndDisplayChart(sensorId, libraryPlantId, managedPlantId) {
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
            if (historyData.length === 0) {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.textAlign = 'center';
                ctx.fillStyle = '#6c757d';
                ctx.fillText('No soil moisture data available for the last 30 days.', canvas.width / 2, canvas.height / 2);
                return;
            }

            const labels = historyData.map(d => new Date(d.timestamp));
            const soilData = historyData.map(d => d.soil_moisture);

            // Configure annotations for threshold lines
            const annotations = {};
            if (profileData.soil_moisture_dry_threshold_voltage) {
                annotations.dryLine = {
                    type: 'line', yMin: profileData.soil_moisture_dry_threshold_voltage, yMax: profileData.soil_moisture_dry_threshold_voltage,
                    borderColor: 'rgb(220, 53, 69, 0.7)', borderWidth: 2, borderDash: [6, 6],
                    label: { content: 'Dry', display: true, position: 'end', color: 'rgb(220, 53, 69, 0.9)', font: {weight: 'bold'} }
                };
            }
            if (profileData.soil_moisture_wet_threshold_voltage) {
                annotations.wetLine = {
                    type: 'line', yMin: profileData.soil_moisture_wet_threshold_voltage, yMax: profileData.soil_moisture_wet_threshold_voltage,
                    borderColor: 'rgb(13, 110, 253, 0.7)', borderWidth: 2, borderDash: [6, 6],
                    label: { content: 'Wet', display: true, position: 'start', color: 'rgb(13, 110, 253, 0.9)', font: {weight: 'bold'} }
                };
            }

            chartInstance = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Soil Moisture (V)',
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
                        y: { title: { display: true, text: 'Sensor Voltage (V)' } }
                    },
                    plugins: {
                        annotation: { annotations: annotations }
                    }
                }
            });
        } catch (error) {
            console.error('Chart display error:', error);
            showAlert('danger', 'Failed to load chart data.', 'main-alert-box');
        } finally {
            loader.classList.add('d-none');
            canvas.style.visibility = 'visible';
        }
    }
}