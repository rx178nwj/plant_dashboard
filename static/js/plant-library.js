/**
 * plant-library.js
 * Plant Libraryページのインタラクションを管理します。
 */

function initializePlantLibrary() {
    // DOM要素のセレクタ
    const addPlantBtn = document.getElementById('add-plant-btn');
    const aiLookupBtn = document.getElementById('ai-lookup-btn');
    const savePlantBtn = document.getElementById('save-plant-btn');
    const deletePlantBtn = document.getElementById('delete-plant-btn');
    const plantList = document.getElementById('plant-list');
    const editorArea = document.getElementById('plant-editor-area');
    const placeholder = document.getElementById('plant-editor-placeholder');
    const plantForm = document.getElementById('plant-form');
    const editorTitle = document.getElementById('editor-title');
    const imagePreview = document.getElementById('plant-image-preview');
    const imageUrlInput = document.getElementById('image-url');
    const imageUploadInput = document.getElementById('plant-image-upload');
    const monthlyTempsTbody = document.getElementById('monthly-temps-tbody');
    
    // 埋め込まれたJSONデータを安全に読み込む
    const serverDataElement = document.getElementById('server-data');
    const plantsData = serverDataElement ? JSON.parse(serverDataElement.textContent) : [];

    // --- ▼▼▼ ヘルパー関数を先に定義 ▼▼▼ ---

    // 画像ソースの表示を切り替える関数
    const toggleImageSource = () => {
        const source = document.querySelector('input[name="image-source"]:checked').value;
        document.getElementById('image-url-group').style.display = (source === 'url') ? 'block' : 'none';
        document.getElementById('image-upload-group').style.display = (source === 'upload') ? 'block' : 'none';
    };

    // 月間気候データをテーブルに描画する関数
    const populateMonthlyTemps = (temps) => {
        monthlyTempsTbody.innerHTML = ''; // テーブルをクリア
        if (!temps) return;

        const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
        months.forEach(month => {
            const monthData = temps[month] || {};
            const row = `
                <tr>
                    <td>${month.charAt(0).toUpperCase() + month.slice(1)}</td>
                    <td>${monthData.avg ?? '--'}</td>
                    <td>${monthData.high ?? '--'}</td>
                    <td>${monthData.low ?? '--'}</td>
                </tr>
            `;
            monthlyTempsTbody.insertAdjacentHTML('beforeend', row);
        });
    };
    
    // フォームにデータを投入する関数
    const populatePlantForm = (data, keepUserInput = false) => {
        if (!data) return;
        
        if (!keepUserInput) {
            plantForm.reset();
        }

        for (const key in data) {
            const value = data[key];
            if (value !== null && value !== undefined) {
                // ネストされた monthly_temps オブジェクトは別途処理
                if (key === 'monthly_temps' && typeof value === 'object') {
                    populateMonthlyTemps(value);
                } else {
                    const el = plantForm.querySelector(`[name="${key}"]`);
                    if (el) {
                        if (keepUserInput && ['genus', 'species', 'variety'].includes(key)) {
                            continue;
                        }
                        el.value = value;
                    }
                }
            }
        }
        editorTitle.textContent = `Editing: ${data.genus || ''} ${data.species || ''}`.trim();

        if (data.image_url) {
            imagePreview.src = data.image_url;
            imageUrlInput.value = data.image_url;
            document.getElementById('image-source-url').checked = true;
        } else {
            imagePreview.src = 'https://placehold.co/600x300/eee/ccc?text=Plant+Image';
        }
        toggleImageSource();
    };

    // フォームの内容をJSONオブジェクトに変換する関数
    const formToJSON = (form) => {
        const data = {};
        const formData = new FormData(form);
        for (const [key, value] of formData.entries()) {
            if (!key.startsWith('plant-image-upload') && !key.startsWith('image-source')) {
                 data[key] = value;
            }
        }
        // monthly_temps は別途構築する必要があるかもしれないが、
        // 現状はサーバー側でjson文字列として保存しているのでこのままでOK
        return data;
    };

    // --- ▲▲▲ ヘルパー関数の定義ここまで ▲▲▲ ---


    // --- イベントリスナー ---

    // 「New」ボタン
    addPlantBtn.addEventListener('click', () => {
        plantForm.reset();
        plantList.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
        editorTitle.textContent = 'New Plant';
        imagePreview.src = 'https://placehold.co/600x300/eee/ccc?text=Plant+Image';
        monthlyTempsTbody.innerHTML = ''; // 気候テーブルをクリア
        document.getElementById('image-source-url').checked = true;
        toggleImageSource(); 
        placeholder.style.display = 'none';
        editorArea.style.display = 'block';
    });
    
    // 植物リストのクリック
    plantList.addEventListener('click', (e) => {
        e.preventDefault();
        const target = e.target.closest('.list-group-item');
        if (!target) return;

        // 埋め込まれた`plantsData`から植物情報を検索
        const plant = plantsData.find(p => p.plant_id === target.dataset.plantId);
        
        if (plant) {
            plantList.querySelectorAll('.list-group-item').forEach(el => el.classList.remove('active'));
            target.classList.add('active');
            
            populatePlantForm(plant);
            
            placeholder.style.display = 'none';
            editorArea.style.display = 'block';
        }
    });

    // 「Save」ボタン
    savePlantBtn.addEventListener('click', async () => {
        const plantData = formToJSON(plantForm);
        const imageSource = document.querySelector('input[name="image-source"]:checked').value;
        const imageFile = imageUploadInput.files[0];

        savePlantBtn.disabled = true;
        savePlantBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Saving...`;

        try {
            // 画像アップロードが選択されている場合、先に画像をアップロード
            if (imageSource === 'upload' && imageFile) {
                const formData = new FormData();
                formData.append('plant-image-upload', imageFile);
                const uploadResponse = await fetch('/api/plants/upload-image', {
                    method: 'POST',
                    body: formData
                });
                const uploadResult = await uploadResponse.json();
                if (!uploadResult.success) {
                    throw new Error(uploadResult.message || 'Image upload failed.');
                }
                plantData.image_url = uploadResult.url;
            }

            // 植物情報を保存
            const saveResponse = await fetch('/api/plants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(plantData)
            });
            const saveResult = await saveResponse.json();
            if (!saveResult.success) {
                throw new Error(saveResult.message || 'Failed to save plant info.');
            }
            
            showAlert('success', `Plant "${plantData.genus} ${plantData.species}" saved successfully! Page will reload.`, 'main-alert-box');
            setTimeout(() => window.location.reload(), 2000);

        } catch (error) {
            showAlert('danger', `Error: ${error.message}`, 'main-alert-box');
        } finally {
            savePlantBtn.disabled = false;
            savePlantBtn.innerHTML = 'Save Plant Info';
        }
    });

    // 「Delete」ボタン
    deletePlantBtn.addEventListener('click', async () => {
        const plantId = document.getElementById('plant-id').value;
        if (!plantId) return;

        if (confirm('Are you sure you want to delete this plant from the library? This action cannot be undone.')) {
            deletePlantBtn.disabled = true;
            deletePlantBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Deleting...`;
            try {
                const response = await fetch(`/api/plants/${plantId}`, {
                    method: 'DELETE',
                });
                const result = await response.json();
                if (!response.ok || !result.success) {
                    throw new Error(result.message || 'Failed to delete plant.');
                }
                showAlert('success', 'Plant deleted successfully! Page will reload.', 'main-alert-box');
                setTimeout(() => window.location.reload(), 2000);
            } catch (error) {
                showAlert('danger', `Error: ${error.message}`, 'main-alert-box');
            } finally {
                deletePlantBtn.disabled = false;
                deletePlantBtn.innerHTML = 'Delete';
            }
        }
    });
    
    // AI検索ボタン
    aiLookupBtn.addEventListener('click', async () => {
        const genus = document.getElementById('genus').value;
        const species = document.getElementById('species').value;
        const variety = document.getElementById('variety').value;
        if (!genus && !species) {
            showAlert('warning', 'Please enter at least a Genus or Species to search.', 'main-alert-box');
            return;
        }

        aiLookupBtn.disabled = true;
        aiLookupBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Searching...`;

        try {
            const response = await fetch('/api/plants/lookup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ genus, species, variety })
            });
            const result = await response.json();
            if (result.success) {
                populatePlantForm(result.data, true); // keepUserInput = true
                showAlert('success', 'AI search successful! Data has been populated.', 'main-alert-box');
            } else {
                throw new Error(result.message || 'AI search failed.');
            }
        } catch (error) {
            showAlert('danger', `Error: ${error.message}`, 'main-alert-box');
        } finally {
            aiLookupBtn.disabled = false;
            aiLookupBtn.innerHTML = '<i class="bi bi-robot"></i> Search with AI';
        }
    });

    // 画像ソースのラジオボタン
    document.querySelectorAll('input[name="image-source"]').forEach(radio => {
        radio.addEventListener('change', toggleImageSource);
    });

    // 画像URL入力
    imageUrlInput.addEventListener('input', (e) => {
        imagePreview.src = e.target.value || 'https://placehold.co/600x300/eee/ccc?text=Plant+Image';
    });

    // 画像ファイル選択
    imageUploadInput.addEventListener('change', () => {
        const file = imageUploadInput.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                imagePreview.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }
    });
}