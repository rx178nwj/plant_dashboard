// plant_dashboard/static/js/utils.js

/**
 * ページの上部にアラートメッセージを表示する
 * @param {string} type - アラートの種類 (e.g., 'success', 'warning', 'danger')
 * @param {string} message - 表示するメッセージ
 * @param {string} containerId - アラートを表示するコンテナのID
 */
function showAlert(type, message, containerId = 'main-alert-box') {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Alert container with id '${containerId}' not found.`);
        return;
    }

    const alertEl = document.createElement('div');
    alertEl.className = `alert alert-${type} alert-dismissible fade show mt-3`;
    alertEl.role = 'alert';
    alertEl.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    // 既存のアラートをクリアしてから新しいアラートを追加
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    container.appendChild(alertEl);

    // 5秒後に自動で消えるタイマー
    setTimeout(() => {
        if (alertEl) {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
            if(bsAlert) bsAlert.close();
        }
    }, 5000);
}
