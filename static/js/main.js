// plant_dashboard/static/js/main.js

/**
 * DOMContentLoadedイベントリスナー
 * ページのHTMLが完全に読み込まれ、解析された後に実行される。
 * ページのIDをチェックし、対応する初期化関数を呼び出す。
 */
document.addEventListener('DOMContentLoaded', function() {
    // ページ上の要素の存在を確認して、対応する初期化関数を呼び出す
    if (document.getElementById('dashboard-page')) {
        initializeDashboard();
    }
    // グラフを持つページで共通のセンサーチャート初期化を呼び出す
    if (document.getElementById('dashboard-page') || document.getElementById('plant-detail-page')) {
        initializePageCharts();
    }
    // 詳細ページで分析チャートを初期化
    if (document.getElementById('plant-detail-page')) {
        initializeAnalysisCharts();
    }
    if (document.getElementById('devices-page')) {
        initializeDeviceManagement();
    }
    if (document.getElementById('plants-page')) {
        initializePlantLibrary();
    }
    if (document.getElementById('management-page')) {
        initializeManagementDashboard();
    }
});

