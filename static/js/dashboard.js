// static/js/dashboard.js

/**
 * ダッシュボードページのUIとイベントを管理するクラス
 */
class DashboardApp {
    constructor() {
        this.container = document.getElementById('dashboard-page');
        if (!this.container) return;

        this.selectedDate = this.container.dataset.selectedDate;
        this.isToday = this.container.dataset.isToday === 'True';
        this.chartInstances = {};

        this.init();
    }

    /**
     * アプリケーションを初期化
     */
    init() {
        this.initDatePicker();
        this.initCharts();
        
        // 今日の日付が表示されている場合のみ、リアルタイム更新を有効化
        if (this.isToday) {
            this.initSse();
        } else {
            console.log("Viewing historical data. Live updates are disabled.");
        }
    }

    /**
     * 日付ピッカーのイベントリスナーを設定
     */
    initDatePicker() {
        const datePicker = document.getElementById('dashboard-date-picker');
        if (datePicker) {
            datePicker.addEventListener('change', (e) => {
                window.location.href = `/?date=${e.target.value}`;
            });
        }
    }

    /**
     * Server-Sent Events (SSE) を初期化してリアルタイム更新を開始
     */
    initSse() {
        const eventSource = new EventSource("/stream");
        eventSource.onmessage = (event) => {
            const devices = JSON.parse(event.data);
            this.updateDeviceCards(devices);
        };
    }

    /**
     * ページ内の全てのチャートを初期化
     */
    initCharts() {
        const chartCanvases = this.container.querySelectorAll('canvas[id^="history-chart-"]');
        chartCanvases.forEach(canvas => {
            const deviceId = canvas.id.replace('history-chart-', '');
            this.updateHistoryChart(deviceId, '24h'); // 初期表示は24時間
        });

        this.container.querySelectorAll('.period-btn').forEach(button => {
            button.addEventListener('click', (e) => {
                const { deviceId, period } = e.target.dataset;
                this.container.querySelectorAll(`.period-btn[data-device-id="${deviceId}"]`).forEach(btn => btn.classList.remove('active'));
                e.target.classList.add('active');
                this.updateHistoryChart(deviceId, period);
            });
        });
    }

    /**
     * 指定されたデバイスの履歴データを取得し、グラフを更新する
     * @param {string} deviceId - デバイスID
     * @param {string} period - 表示期間 ('24h', '7d', '30d', '1y')
     */
    async updateHistoryChart(deviceId, period) {
        const canvas = document.getElementById(`history-chart-${deviceId}`);
        const loader = document.getElementById(`chart-loader-${deviceId}`);
        if (!canvas || !loader) return;

        const ctx = canvas.getContext('2d');
        if (this.chartInstances[deviceId]) {
            this.chartInstances[deviceId].destroy();
        }

        loader.classList.remove('d-none');
        canvas.style.visibility = 'hidden';

        try {
            const response = await fetch(`/api/history/${deviceId}?period=${period}&date=${this.selectedDate}`);
            if (!response.ok) throw new Error(`API request failed with status ${response.status}`);
            
            const historyData = await response.json();
            if (historyData.length === 0) {
                this.drawNoDataMessage(ctx, canvas);
                return;
            }

            const labels = historyData.map(d => new Date(d.timestamp));
            let timeUnit = 'hour';
            if (period === '7d' || period === '30d') timeUnit = 'day';
            else if (period === '1y') timeUnit = 'month';

            this.chartInstances[deviceId] = new Chart(ctx, this.getChartConfig(labels, historyData, timeUnit));

        } catch (error) {
            console.error(`Failed to update chart for ${deviceId}:`, error);
            this.drawErrorMessage(ctx, canvas);
        } finally {
            loader.classList.add('d-none');
            canvas.style.visibility = 'visible';
        }
    }
    
    /**
     * チャートに「データなし」メッセージを描画
     */
    drawNoDataMessage(ctx, canvas) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.textAlign = 'center';
        ctx.fillStyle = '#6c757d';
        ctx.font = '16px sans-serif';
        ctx.fillText('No data available for this period.', canvas.width / 2, canvas.height / 2);
    }

    /**
     * チャートにエラーメッセージを描画
     */
    drawErrorMessage(ctx, canvas) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.textAlign = 'center';
        ctx.fillStyle = '#dc3545';
        ctx.font = '16px sans-serif';
        ctx.fillText('Failed to load chart data.', canvas.width / 2, canvas.height / 2);
    }

    /**
     * Chart.js の設定オブジェクトを生成して返す
     */
    getChartConfig(labels, data, timeUnit) {
        return {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Temperature (°C)',
                        data: data.map(d => d.temperature),
                        borderColor: 'rgba(220, 53, 69, 0.8)',
                        backgroundColor: 'rgba(220, 53, 69, 0.1)',
                        yAxisID: 'y_temp',
                        tension: 0.2, fill: true, pointRadius: 1, pointHoverRadius: 5
                    },
                    {
                        label: 'Humidity (%)',
                        data: data.map(d => d.humidity),
                        borderColor: 'rgba(13, 110, 253, 0.8)',
                        backgroundColor: 'rgba(13, 110, 253, 0.1)',
                        yAxisID: 'y_humid',
                        tension: 0.2, fill: true, pointRadius: 1, pointHoverRadius: 5
                    }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: {
                        type: 'time',
                        time: { unit: timeUnit, tooltipFormat: 'yyyy/MM/dd HH:mm' },
                        ticks: { source: 'auto', maxRotation: 0, autoSkip: true }
                    },
                    y_temp: {
                        type: 'linear', display: true, position: 'left',
                        title: { display: true, text: 'Temperature (°C)', color: 'rgba(220, 53, 69, 1)' }
                    },
                    y_humid: {
                        type: 'linear', display: true, position: 'right',
                        title: { display: true, text: 'Humidity (%)', color: 'rgba(13, 110, 253, 1)' },
                        grid: { drawOnChartArea: false }
                    }
                },
                plugins: {
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)', padding: 10,
                        cornerRadius: 4, titleSpacing: 6, bodySpacing: 4
                    }
                }
            }
        };
    }

    /**
     * デバイスカードの表示をリアルタイムで更新
     */
    updateDeviceCards(devices) {
        devices.forEach(device => {
            this.updateElementText(`temp-${device.device_id}`, device.last_data.temperature?.toFixed(1) || '--');
            this.updateElementText(`humidity-${device.device_id}`, device.last_data.humidity?.toFixed(1) || '--');
            this.updateElementText(`light-${device.device_id}`, device.last_data.light_lux || '--');
            this.updateElementText(`soil-${device.device_id}`, device.last_data.soil_moisture || '--');
            this.updateElementText(`battery-${device.device_id}`, device.battery_level || '--');
            this.updateStatusVisuals(device.device_id, device.connection_status);
        });
    }

    updateElementText(id, text) {
        const element = document.getElementById(id);
        if (element && element.textContent !== text) {
            element.textContent = text;
        }
    }

    updateStatusVisuals(deviceId, status) {
        const card = document.getElementById(`device-card-${deviceId}`);
        const iconElement = document.getElementById(`status-icon-${deviceId}`);
        if (!card || !iconElement) return;

        card.className = card.className.replace(/\bstatus-\S+/g, '');
        card.classList.add(`status-${status}`);

        let iconHtml = '<i class="bi bi-question-circle"></i>';
        switch (status) {
            case 'connected':
            case 'historical':
                iconHtml = '<i class="bi bi-check-circle-fill"></i>'; break;
            case 'disconnected':
                iconHtml = '<i class="bi bi-x-circle-fill"></i>'; break;
            case 'error':
                iconHtml = '<i class="bi bi-exclamation-triangle-fill"></i>'; break;
            case 'no_data':
                iconHtml = '<i class="bi bi-archive-fill"></i>'; break;
        }
        iconElement.innerHTML = iconHtml;
    }
}

// DOMが読み込まれたらDashboardAppをインスタンス化
document.addEventListener('DOMContentLoaded', () => new DashboardApp());
