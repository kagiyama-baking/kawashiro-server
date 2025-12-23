# Weather API（気象庁天気予報）

気象庁の天気予報 API を利用して、指定した地域の天気予報を取得する REST API です。

## エンドポイント

```
GET /weather/forecast/
```

### リクエストパラメータ

| パラメータ  | 型     | 必須 | デフォルト | 説明                                         |
| ----------- | ------ | ---- | ---------- | -------------------------------------------- |
| `area_code` | string | ✅   | -          | 予報区コード（例: `130010`=東京地方）        |
| `day`       | int    | -    | `0`        | 予報日（`0`: 今日, `1`: 明日, `2`: 明後日）  |

### レスポンス

```json
{
    "area_name": "東京都 東京地方",
    "area_code": "130010",
    "date": "2025-12-24",
    "weather": "晴れ　夜　くもり",
    "weather_code": "111",
    "temp_min": 4,
    "temp_max": 10,
    "pop_00_06": 10,
    "pop_06_12": 20,
    "pop_12_18": 30,
    "pop_18_24": 40
}
```

| フィールド     | 型          | 説明                          |
| -------------- | ----------- | ----------------------------- |
| `area_name`    | string      | 地域名（都道府県名 + 地域名） |
| `area_code`    | string      | 予報区コード                  |
| `date`         | string      | 予報日（YYYY-MM-DD）          |
| `weather`      | string      | 天気の説明                    |
| `weather_code` | string      | 天気コード                    |
| `temp_min`     | int \| null | 最低気温（℃）                 |
| `temp_max`     | int \| null | 最高気温（℃）                 |
| `pop_00_06`    | int \| null | 降水確率 0時〜6時（%）        |
| `pop_06_12`    | int \| null | 降水確率 6時〜12時（%）       |
| `pop_12_18`    | int \| null | 降水確率 12時〜18時（%）      |
| `pop_18_24`    | int \| null | 降水確率 18時〜24時（%）      |

## 予報区コード

予報区コードは気象庁が定める 6 桁のコードです。

### コード体系

```
PPPPAA
│││││└─ 地域番号（10, 20, 30...）
└┴┴┴─── 都道府県番号（01〜47）
```

### 主要な予報区コード

| コード   | 地域名             |
| -------- | ------------------ |
| `010010` | 北海道 石狩地方    |
| `040010` | 宮城県 東部        |
| `130010` | 東京都 東京地方    |
| `130020` | 東京都 伊豆諸島北部|
| `140010` | 神奈川県 東部      |
| `230010` | 愛知県 西部        |
| `270000` | 大阪府             |
| `400010` | 福岡県 福岡地方    |
| `471010` | 沖縄県 本島中南部  |

詳細な予報区コード一覧は[気象庁の地域リスト](https://www.jma.go.jp/bosai/common/const/area.json)を参照してください。

## 特殊仕様

### 深夜帯のデータ調整（0:00〜5:00 JST）

気象庁の天気予報 API は、毎日 5:00、11:00、17:00 頃に更新されます。
そのため、**深夜 0:00〜5:00 の間は前日の予報データ**が返されます。

この API では、深夜帯にリクエストされた場合、自動的にデータのインデックスを調整します：

| day パラメータ | 通常時（5:00〜23:59） | 深夜帯（0:00〜4:59）      |
| -------------- | --------------------- | ------------------------- |
| `0`（今日）    | 当日の予報            | 翌日の予報（=実際の今日） |
| `1`（明日）    | 翌日の予報            | 翌々日の予報（=実際の明日）|
| `2`（明後日）  | 翌々日の予報          | 週間予報から取得          |

#### 深夜帯の例

12月24日 午前3時にリクエストした場合：

- `day=0` → 12月24日（今日）の予報を返す（API 上は 12月23日の timeDefines[1]）
- `day=1` → 12月25日（明日）の予報を返す（API 上は 12月23日の timeDefines[2]）
- `day=2` → 12月26日（明後日）の予報を返す（週間予報から取得）

### 気温・降水確率のデータソース

| day | 天気       | 気温               | 降水確率           |
| --- | ---------- | ------------------ | ------------------ |
| `0` | 短期予報   | -（取得不可）      | 18時〜24時のみ     |
| `1` | 短期予報   | 短期予報           | 4時間ごと（4区分） |
| `2` | 短期予報   | 週間予報           | 週間予報（1日1値） |

- **短期予報**: 3日間の詳細予報（timeSeries）
- **週間予報**: 7日間の概況予報（週間天気予報）

### 週間予報の降水確率

`day=2`（明後日）の場合、週間予報から1日単位の降水確率を取得し、全時間帯（`pop_00_06`, `pop_06_12`, `pop_12_18`, `pop_18_24`）に同じ値を設定します。

## エラーレスポンス

### 400 Bad Request

リクエストパラメータが不正な場合：

```json
{
    "area_code": ["この項目は必須です。"],
    "day": ["この値は2以下でなければなりません。"]
}
```

### 401 Unauthorized

認証トークンが無効または未指定の場合：

```json
{
    "detail": "認証情報が含まれていません。"
}
```

### 404 Not Found

予報区コードが見つからない場合：

```json
{
    "error": "指定された都道府県コード '999900' が見つかりません"
}
```

または：

```json
{
    "error": "指定された予報区コード '130099' が見つかりません"
}
```

### 502 Bad Gateway

気象庁 API への接続に失敗した場合：

```json
{
    "error": "気象庁APIへの接続に失敗しました"
}
```

### 504 Gateway Timeout

気象庁 API がタイムアウトした場合：

```json
{
    "error": "気象庁APIへのリクエストがタイムアウトしました"
}
```

## 使用例

### curl

```bash
# 東京地方の今日の天気
curl -H "Authorization: Token YOUR_API_TOKEN" \
  "http://localhost:8000/weather/forecast/?area_code=130010"

# 大阪府の明日の天気
curl -H "Authorization: Token YOUR_API_TOKEN" \
  "http://localhost:8000/weather/forecast/?area_code=270000&day=1"

# 福岡地方の明後日の天気
curl -H "Authorization: Token YOUR_API_TOKEN" \
  "http://localhost:8000/weather/forecast/?area_code=400010&day=2"
```

### Python

```python
import requests

API_URL = "http://localhost:8000/weather/forecast/"
TOKEN = "YOUR_API_TOKEN"

response = requests.get(
    API_URL,
    headers={"Authorization": f"Token {TOKEN}"},
    params={"area_code": "130010", "day": 0}
)

data = response.json()
print(f"{data['area_name']}の天気: {data['weather']}")
print(f"最高気温: {data['temp_max']}℃ / 最低気温: {data['temp_min']}℃")
```

## 参考資料

- [気象庁天気予報 API](https://www.jma.go.jp/bosai/forecast/)
- [気象庁 地域コード一覧](https://www.jma.go.jp/bosai/common/const/area.json)
- [天気予報コード一覧](https://www.jma.go.jp/bosai/forecast/const/forecast_area.json)
