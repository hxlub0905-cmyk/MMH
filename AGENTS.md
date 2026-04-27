# AGENTS.md — SEM MM 專案總覽文件
# 語言：繁體中文
# 適用對象：接手此專案的 AI Agent 或開發者

---

## 一、專案背景與目的

此專案名稱為 **SEM MM（Massive Measurement）**，是一套半導體製程 SEM（掃描式電子顯微鏡）影像自動化 CD（Critical Dimension，臨界尺寸）量測桌面應用程式。

主要量測目標為 **CMG Y-CD（Cut Metal Gate 垂直間距）**：
- MG（Metal Gate）為 SEM 影像中的垂直亮條紋（高灰階值）
- CMG（Cut Metal Gate）是水平方向的切割，將每一根 MG 切成上下兩段
- Y-CD = 上段 MG 底部邊緣 → 下段 MG 頂部邊緣的像素距離 × nm/pixel

```
 col0    col1    col2
|████|  |████|  |████|   ← Upper MG
|    |  |    |  |    |   ← CMG gap（量測此 Y 方向間距）
|████|  |████|  |████|   ← Lower MG
```

---

## 二、技術棧

| 項目 | 選擇 |
|---|---|
| 語言 | Python 3.8+（相容 3.9 以下需 `from __future__ import annotations`） |
| GUI | PyQt6 |
| 影像處理 | OpenCV (`cv2`)、scikit-image、NumPy |
| 資料輸出 | pandas、openpyxl、matplotlib |
| 平行處理 | `concurrent.futures.ProcessPoolExecutor` |
| 目標 OS | Windows 10/11（跨平台相容） |

---

## 三、專案目錄結構

```
MMH/
├── main.py                        ← 程式入口（含 freeze_support，Windows 多進程安全）
├── requirements.txt               ← 相依套件清單
├── AGENTS.md                      ← 本文件
├── logs/                          ← Session 交接日誌
│   └── session_YYYY-MM-DD.md
├── tests/
│   └── test_cmg_analyzer.py       ← 10 項單元測試
└── src/
    ├── core/                      ← 核心演算法（不含 GUI）
    │   ├── image_loader.py        ← 載入 TIFF/PNG/JPEG/BMP → uint8 灰階
    │   ├── preprocessor.py        ← Gaussian → CLAHE → GL Range mask → Morph
    │   ├── mg_detector.py         ← 連通元件分析 → Blob 列表
    │   ├── cmg_analyzer.py        ← X-range 分欄 → Y-gap 配對 → CMG 聚類 → Y-CD
    │   └── annotator.py           ← 在影像上繪製量測線、數值、邊框
    ├── gui/                       ← 介面元件
    │   ├── styles.py              ← 全域 QSS 深色主題
    │   ├── main_window.py         ← 主視窗（三欄布局）
    │   ├── image_viewer.py        ← QGraphicsView（縮放/平移）
    │   ├── file_tree_panel.py     ← QTreeWidget 檔案瀏覽（支援影像格式過濾）
    │   ├── control_panel.py       ← 右側控制面板（GL Range、形態學參數）
    │   ├── results_panel.py       ← 底部量測結果表格
    │   └── batch_dialog.py        ← 批量處理進度對話框
    └── output/                    ← 輸出模組
        ├── _common.py             ← 共用 DataFrame 轉換
        ├── csv_exporter.py
        ├── excel_exporter.py
        ├── json_exporter.py
        └── report_generator.py    ← HTML 報告含 matplotlib 直方圖
```

---

## 四、核心演算法流程

### 4.1 前處理 Pipeline（preprocessor.py）

```
輸入 uint8 灰階影像
  ↓ Gaussian Blur（kernel 可調，預設 3px）
  ↓ CLAHE 對比正規化（可關閉）
  ↓ GL Range Mask：cv2.inRange(gl_min, gl_max)  ← 雙向閾值
  ↓ Morphological Open（去除噪點，預設 3px）
  ↓ Morphological Close（填補孔洞，預設 5px）
輸出 Binary Mask（255=MG, 0=背景）
```

### 4.2 CMG Y-CD 演算法（cmg_analyzer.py）

```
Step 1：連通元件分析 → Blob 列表（mg_detector.py）
         過濾面積 < min_area 的小 blob

Step 2：X-range 重疊分組（Union-Find）
         overlap_ratio = overlap / min(width_a, width_b)
         若 > 0.5 → 同一 MG 欄（column）

Step 3：同欄內按 Y 排序 → 相鄰 blob 對 → candidate gap
         Y-CD_px = y_top(lower) - y_bottom(upper)  [> 0 才有效]

Step 4：跨欄聚類（gap_mid_y 相差 < Y_CLUSTER_TOL=10px → 同一 CMG cut）

Step 5：每個 CMG cut 內標記 MIN（紅）/ MAX（藍）
         輸出 YCDMeasurement 列表
```

### 4.3 Annotated 覆蓋層（annotator.py）

- `OverlayOptions(show_lines, show_labels, show_boxes)` 控制顯示項目
- **Labels**：只顯示純數字（如 `12.5`），無單位、無前綴、無背景框
- **三色**：MIN=紅(#e05555)、MAX=藍(#5588ee)、正常=青(#44aadd)
- Mask 疊層僅在「Mask」模式顯示，「Annotated」模式不顯示 mask

---

## 五、GUI 架構

### 5.1 三欄布局

```
┌──────────────────────────────────────────────────────────────────┐
│  MenuBar + ToolBar                                               │
├───────────┬──────────────────────────────────────┬──────────────┤
│  Files    │  [Raw][Mask][Annotated] | ☑Lines      │  Scale       │
│  (Tree)   │  ☑Values ☑Boxes        | hint        │  Detection   │
│           ├──────────────────────────────────────┤  GL Min ──●  │
│  image1   │                                      │  GL Max ──●  │
│  image2   │     ImageViewer                      │  Min Area    │
│  ...      │     (Zoom/Pan)                       ├──────────────┤
│           ├──────────────────────────────────────┤  Pre-proc    │
│           │  Results Table                       │  Gaussian    │
│           │  CMG│Col│px│nm│Flag│Status           │  Morph O/C   │
└───────────┴──────────────────────────────────────┴──────────────┘
│  Status Bar                                                      │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Viewer 模式切換

| 模式 | 顯示內容 | Overlay 選項顯示 |
|---|---|---|
| Raw | 原始灰階影像 | 隱藏 |
| Mask | 灰階 + 青色 MG 遮罩 | 隱藏 |
| Annotated | 灰階 + 量測線/數值/框 | **顯示**（Lines/Values/Boxes） |

### 5.3 即時預覽機制

- 任何參數變更 → 啟動 150ms debounce timer → 對當前影像重新跑 preprocess → 更新 viewer

---

## 六、資料流與輸出格式

### 批量處理輸出（Export 後）

| 檔案 | 內容 |
|---|---|
| `{ts}_measurements.csv` | 每張影像 × 每個 CMG × 每欄的 Y-CD 數值 |
| `{ts}_measurements.xlsx` | 同上 + Statistics 頁（mean/median/std/3σ/min/max）+ 紅藍標色 |
| `{ts}_measurements.json` | 結構化巢狀 JSON |
| `{ts}_report.html` | 統計摘要 + matplotlib 直方圖（mean ±3σ 標線） |
| `annotated/{name}_annotated.png` | 含量測標注的輸出影像 |
| `_failed/{name}` | 偵測失敗的原始影像副本 |

### CSV/Excel 欄位

`image_file | nm_per_pixel | cmg_id | col_id | y_cd_px | y_cd_nm | flag | upper_bbox | lower_bbox | status | error`

---

## 七、已知限制與注意事項

1. **Python 版本相容性**：所有 `.py` 檔必須有 `from __future__ import annotations`，否則 Python 3.9 以下會因 `X | Y` 語法報 `TypeError`。
2. **QFileSystemModel 已移除**：`PyQt6` 新版不再提供 `QFileSystemModel`，`file_tree_panel.py` 改用 `QTreeWidget` 手動掃描目錄。
3. **多進程 Windows 安全**：`main.py` 必須保留 `freeze_support()` 與 `if __name__ == '__main__':` 守衛，否則 Windows 下 batch 處理會無限 spawn 子進程。
4. **CLAHE 後的 GL 範圍**：CLAHE 正規化會改變像素的 GL 分佈，使用者需在 CLAHE 開啟狀態下重新校正 GL Min/Max。
5. **Y_CLUSTER_TOL 固定為 10px**：如影像解析度很低，相鄰 CMG 可能被誤合併；此參數目前硬編碼在 `cmg_analyzer.py` 頂部，可在未來加入 UI 設定。

---

## 八、尚未實作（Phase 2）

- [ ] KLARF 整合（lot/wafer/die metadata 對應）
- [ ] Recipe 管理（儲存/載入參數組合）
- [ ] GPU 加速（大批量超高解析度場景）
- [ ] GDS-based ROI 定義（複雜 layout）
- [ ] Y_CLUSTER_TOL UI 設定
- [ ] 影像縮放比例顯示（viewer header zoom% label 目前為靜態文字）

---

## 九、開發與測試

```bash
# 安裝相依
pip install -r requirements.txt

# 執行測試（10 項單元測試，覆蓋 cmg_analyzer 核心邏輯）
python -m pytest tests/ -v

# 啟動應用程式
python main.py
```

---

## 十、分支資訊

- **開發分支**：`claude/sem-measurement-app-XudV6`
- **Remote**：`hxlub0905-cmyk/MMH`
- 每次 Session 結束後需 push 至此分支，並在 `logs/` 新增 session log。
