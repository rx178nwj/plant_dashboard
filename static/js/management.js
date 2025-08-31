// plant_dashboard/static/js/management.js

function initializeManagementDashboard() {
    const addPlantBtn = document.getElementById('add-managed-plant-btn');
    const savePlantBtn = document.getElementById('save-managed-plant-btn');
    const deletePlantBtn = document.getElementById('delete-managed-plant-btn');
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
        savePlantBtn.disabled = true;
        savePlantBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;
        try {
            const response = await fetch('/api/managed-plants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(plantData)
            });
            const result = await response.json();
            if (!response.ok || !result.success) { throw new Error('Failed to save plant.'); }
            loadManagedPlants();
            showAlert('success', 'Managed plant saved successfully.', 'main-alert-box');
            editorArea.style.display = 'none';
            placeholder.style.display = 'block';
        } catch (error) {
            showAlert('danger', `Error saving plant: ${error.message}`, 'main-alert-box');
        } finally {
            savePlantBtn.disabled = false;
            savePlantBtn.innerHTML = 'Save Changes';
        }
    });

    deletePlantBtn.addEventListener('click', async () => {
        const managedPlantId = document.getElementById('managed-plant-id').value;
        if (!managedPlantId) return;

        if (confirm('Are you sure you want to delete this plant?')) {
            deletePlantBtn.disabled = true;
            deletePlantBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Deleting...`;
            try {
                const response = await fetch(`/api/managed-plants/${managedPlantId}`, {
                    method: 'DELETE',
                });
                const result = await response.json();
                if (!response.ok || !result.success) { throw new Error('Failed to delete plant.'); }
                loadManagedPlants();
                showAlert('success', 'Managed plant deleted successfully.', 'main-alert-box');
                editorArea.style.display = 'none';
                placeholder.style.display = 'block';
            } catch (error) {
                showAlert('danger', `Error deleting plant: ${error.message}`, 'main-alert-box');
            } finally {
                deletePlantBtn.disabled = false;
                deletePlantBtn.innerHTML = 'Delete';
            }
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