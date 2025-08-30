# read_db.py
import sqlite3
import os

# プロジェクトのベースディレクトリを特定
# このスクリプトがプロジェクトルートにあることを想定
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'plant_monitor.db')

def read_latest_sensor_data(limit=10):
    """
    sensor_dataテーブルから最新のデータを指定された件数だけ読み込む
    """
    if not os.path.exists(DATABASE_PATH):
        print(f"エラー: データベースファイルが見つかりません: {DATABASE_PATH}")
        return

    try:
        # データベースに接続
        conn = sqlite3.connect(DATABASE_PATH)
        # カラム名でアクセスできるようにする
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        print(f"--- 最新のセンサーデータを{limit}件表示 ---")

        # devicesテーブルとJOINして、デバイス名も一緒に取得する
        # timestampの降順（新しい順）で並べ替え、件数を制限する
        cursor.execute("""
            SELECT
                sd.timestamp,
                d.device_name,
                sd.temperature,
                sd.humidity
            FROM sensor_data sd
            JOIN devices d ON sd.device_id = d.device_id
            ORDER BY sd.timestamp DESC
            LIMIT ?
        """, (limit,))

        # 結果を取得
        rows = cursor.fetchall()

        if not rows:
            print("センサーデータが見つかりませんでした。")
            return

        # 結果を整形して表示
        for row in rows:
            print(
                f"[{row['timestamp']}] "
                f"デバイス名: {row['device_name']:<25} | "
                f"温度: {row['temperature']:.1f}°C | "
                f"湿度: {row['humidity']:.1f}%"
            )

    except sqlite3.Error as e:
        print(f"データベースエラーが発生しました: {e}")
    finally:
        # 接続を閉じる
        if conn:
            conn.close()

if __name__ == "__main__":
    read_latest_sensor_data()