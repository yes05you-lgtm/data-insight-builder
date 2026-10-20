import math
import re
import pandas as pd

# 집계 행 감지에 사용할 표준 키워드 목록
DEFAULT_AGGREGATE_KEYWORDS = [
    "world", "oecd", "euro area", "european union", "income", "area", "total",
    "dividend", "ida & ibrd", "caribbean", "small states", "latin america",
    "middle east", "north africa", "sub-saharan", "south asia", "east asia"
]


def sanitize_data(obj):
    """
    Pandas 계산 결과 중 NaN, Infinity를 JSON 직렬화가 가능한 None으로 변환
    """
    if isinstance(obj, dict):
        return {k: sanitize_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_data(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 4)
    elif pd.isna(obj):
        return None
    return obj


def is_aggregate_row(val_str: str, keywords=None) -> bool:
    """주어진 문자열이 집계/지역/그룹 행 키워드를 포함하는지 검사"""
    if not val_str:
        return False
    if keywords is None:
        keywords = DEFAULT_AGGREGATE_KEYWORDS
    lowered = str(val_str).lower()
    return any(kw in lowered for kw in keywords)


def get_default_label_column(df: pd.DataFrame) -> str:
    """데이터프레임의 첫 번째 유효 라벨(문자형) 열 탐색"""
    cols = [str(c) for c in df.columns]
    str_cols = [c for c in cols if not re.match(r"^(19|20)\d{2}$", str(c).strip()) and not str(c).startswith("Unnamed:")]
    return str_cols[0] if str_cols else cols[0]


# ==============================================================================
# 도구 1. reshape_wide_to_long (연도 열을 행으로 접기)
# ==============================================================================
def reshape_wide_to_long(df: pd.DataFrame, id_vars=None, value_name="value", var_name="year", **kwargs):
    """
    와이드(가로) 포맷의 연도 열들을 롱(세로) 포맷으로 변환합니다.
    """
    total_rows = len(df)
    cols = [str(c) for c in df.columns]

    year_cols = [c for c in cols if re.match(r"^(19|20)\d{2}$", str(c).strip())]
    if not year_cols:
        return {
            "tool": "reshape_wide_to_long",
            "success": False,
            "error": "변환할 연도 열(예: 1960~2025)을 찾지 못했습니다."
        }

    if not id_vars:
        id_vars = [c for c in cols if c not in year_cols and not str(c).startswith("Unnamed:")]

    melted_df = pd.melt(
        df,
        id_vars=id_vars,
        value_vars=year_cols,
        var_name=var_name,
        value_name=value_name
    )

    original_melted_len = len(melted_df)
    valid_melted = melted_df.dropna(subset=[value_name])
    dropped_count = original_melted_len - len(valid_melted)
    preview = valid_melted.head(20).to_dict(orient="records")

    return {
        "tool": "reshape_wide_to_long",
        "success": True,
        "reference_period": f"{year_cols[0]} ~ {year_cols[-1]} (전체 {len(year_cols)}개 연도)",
        "rows_used": total_rows,
        "rows_excluded": 0,
        "exclusion_reason": None,
        "columns_used": id_vars + year_cols,
        "unit": "행 수 (변환 후)",
        "caution": f"와이드 형식의 {len(year_cols)}개 연도 열을 행으로 변환했습니다. (결측치 {dropped_count}개 제외 후 유효 행 {len(valid_melted)}건)",
        "result": {
            "id_columns": id_vars,
            "year_columns_count": len(year_cols),
            "total_reshaped_rows": len(melted_df),
            "valid_rows_count": len(valid_melted),
            "preview": sanitize_data(preview)
        }
    }


# ==============================================================================
# 도구 2. quality_report (결측·중복·타입·이상한 열 이름 진단 보고서)
# ==============================================================================
def quality_report(df: pd.DataFrame, **kwargs):
    """
    데이터셋의 결측률, 중복 행, 데이터 타입 및 이상 열 이름 보고서를 생성합니다.
    """
    total_rows = len(df)
    cols = [str(c) for c in df.columns]

    missing_info = []
    abnormal_cols = []

    for col in cols:
        m_count = int(df[col].isna().sum())
        m_ratio = round(float(m_count / total_rows), 4) if total_rows > 0 else 0.0
        missing_info.append({
            "column": col,
            "missing_count": m_count,
            "missing_ratio": m_ratio,
            "dtype": str(df[col].dtype)
        })

        if str(col).startswith("Unnamed:") or col.strip() == "" or col != col.strip():
            abnormal_cols.append(col)

    duplicate_count = int(df.duplicated().sum())

    return {
        "tool": "quality_report",
        "success": True,
        "reference_period": "전체 데이터셋",
        "rows_used": total_rows,
        "rows_excluded": 0,
        "exclusion_reason": None,
        "columns_used": cols,
        "unit": "건 / 비율",
        "caution": "결측률이 50%를 넘는 열이나 이름 없는 열은 분석에서 제외하거나 처리 후 사용해야 왜곡을 막을 수 있습니다.",
        "result": {
            "total_rows": total_rows,
            "total_columns": len(cols),
            "duplicate_rows": duplicate_count,
            "abnormal_columns": abnormal_cols,
            "column_quality": sanitize_data(missing_info)
        }
    }


# ==============================================================================
# 도구 3. year_coverage (연도별 값 개수와 권장 기준연도)
# ==============================================================================
def year_coverage(df: pd.DataFrame, **kwargs):
    """
    각 연도별 데이터의 유효 관측치 수와 충실도를 계산하고 권장 기준연도를 제안합니다.
    """
    total_rows = len(df)
    cols = [str(c) for c in df.columns]
    year_cols = [c for c in cols if re.match(r"^(19|20)\d{2}$", str(c).strip())]

    if not year_cols:
        return {
            "tool": "year_coverage",
            "success": False,
            "error": "연도 형태의 열(예: 1960~2025)을 찾지 못했습니다."
        }

    year_stats = []
    coverage_dict = {}

    for y in year_cols:
        filled = int(df[y].notna().sum())
        ratio = round(float(filled / total_rows), 4) if total_rows > 0 else 0.0
        year_stats.append({
            "year": y,
            "filled_count": filled,
            "missing_count": total_rows - filled,
            "coverage_ratio": ratio
        })
        coverage_dict[y] = filled

    max_filled = max(coverage_dict.values()) if coverage_dict else 0
    rec_candidates = [
        y for y, count in coverage_dict.items()
        if count >= max_filled * 0.85 and count > 0
    ]
    recommended_year = rec_candidates[-1] if rec_candidates else (year_cols[-1] if year_cols else None)

    chart_data = {
        "type": "line",
        "labels": year_cols,
        "datasets": [{
            "label": "연도별 유효 데이터 수",
            "data": [coverage_dict[y] for y in year_cols],
            "borderColor": "#3b82f6",
            "backgroundColor": "rgba(59, 130, 246, 0.2)",
            "fill": True
        }]
    }

    return {
        "tool": "year_coverage",
        "success": True,
        "reference_period": f"{year_cols[0]} ~ {year_cols[-1]}",
        "rows_used": total_rows,
        "rows_excluded": 0,
        "exclusion_reason": None,
        "columns_used": year_cols,
        "unit": "건 (유효 행 수)",
        "caution": "최신 연도일수록 아직 집계가 끝나지 않아 결측치가 급증할 수 있으므로, 권장 기준연도를 확인하세요.",
        "result": {
            "recommended_year": recommended_year,
            "max_coverage_count": max_filled,
            "yearly_stats": sanitize_data(year_stats)
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 4. detect_aggregates (집계 행 후보 탐지)
# ==============================================================================
def detect_aggregates(df: pd.DataFrame, label_column=None, **kwargs):
    """
    국가명이 아닌 대륙, 소득분류, 전세계 합계 등 집계 행 후보를 탐지합니다.
    """
    total_rows = len(df)
    cols = [str(c) for c in df.columns]

    if not label_column or label_column not in df.columns:
        label_column = get_default_label_column(df)

    aggregates_found = []
    individuals_found = []

    for idx, val in df[label_column].items():
        val_str = str(val) if pd.notna(val) else ""
        if is_aggregate_row(val_str):
            aggregates_found.append({
                "row_index": int(idx),
                "label": val_str
            })
        else:
            individuals_found.append({
                "row_index": int(idx),
                "label": val_str
            })

    return {
        "tool": "detect_aggregates",
        "success": True,
        "reference_period": "전체 데이터셋",
        "rows_used": total_rows,
        "rows_excluded": 0,
        "exclusion_reason": None,
        "columns_used": [label_column],
        "unit": "행 수",
        "caution": "개별 국가 순위나 평균을 낼 때는 집계 행을 반드시 제외해야 중복 합산 왜곡이 발생하지 않습니다.",
        "result": {
            "label_column": label_column,
            "aggregate_count": len(aggregates_found),
            "individual_count": len(individuals_found),
            "aggregate_candidates": sanitize_data(aggregates_found[:50]),
            "individual_sample": sanitize_data(individuals_found[:10])
        }
    }


# ==============================================================================
# 도구 5. describe_numeric (개수·평균·중앙값·최소·최대·표준편차)
# ==============================================================================
def describe_numeric(df: pd.DataFrame, value_column=None, reference_period=None, exclude_aggregates=True, **kwargs):
    """
    선택된 숫자 열 또는 기준 연도 열의 기술통계량(평균, 중앙값, 최솟값, 최댓값, 표준편차)을 계산합니다.
    """
    target_col = value_column or reference_period
    label_col = get_default_label_column(df)

    if not target_col or target_col not in df.columns:
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if num_cols:
            target_col = num_cols[-1]
        else:
            return {
                "tool": "describe_numeric",
                "success": False,
                "error": "통계를 계산할 유효한 숫자 열 또는 연도 열을 찾지 못했습니다."
            }

    working_df = df.copy()
    excluded_reasons = []
    excluded_count = 0

    if exclude_aggregates:
        mask_agg = working_df[label_col].apply(lambda v: is_aggregate_row(str(v)))
        agg_count = int(mask_agg.sum())
        if agg_count > 0:
            working_df = working_df[~mask_agg]
            excluded_count += agg_count
            excluded_reasons.append(f"집계 행(대륙/소득군 등) {agg_count}개 제외")

    series = pd.to_numeric(working_df[target_col], errors="coerce").dropna()
    null_count = len(working_df) - len(series)
    if null_count > 0:
        excluded_count += null_count
        excluded_reasons.append(f"{target_col} 결측치 {null_count}개 제외")

    if len(series) == 0:
        return {
            "tool": "describe_numeric",
            "success": False,
            "error": f"선택한 열 '{target_col}'에 계산 가능한 유효 숫자가 없습니다."
        }

    stats = {
        "count": int(len(series)),
        "mean": round(float(series.mean()), 4),
        "median": round(float(series.median()), 4),
        "min": round(float(series.min()), 4),
        "max": round(float(series.max()), 4),
        "std": round(float(series.std()), 4) if len(series) > 1 else 0.0,
        "q25": round(float(series.quantile(0.25)), 4),
        "q75": round(float(series.quantile(0.75)), 4)
    }

    ref_period = str(reference_period or target_col)
    reason_str = ", ".join(excluded_reasons) if excluded_reasons else None

    return {
        "tool": "describe_numeric",
        "success": True,
        "reference_period": ref_period,
        "rows_used": int(len(series)),
        "rows_excluded": excluded_count,
        "exclusion_reason": reason_str,
        "columns_used": [target_col],
        "unit": "수치 단위 (지표 기준)",
        "caution": "극단치(Outlier)가 있는 경우 평균이 왜곡될 수 있으므로 중앙값과 사분위수 범위를 함께 확인하세요.",
        "result": sanitize_data(stats)
    }


# ==============================================================================
# 도구 6. trend_line (선택 항목들의 연도별 추이 - 선 차트)
# ==============================================================================
def trend_line(df: pd.DataFrame, items=None, label_column=None, year_columns=None, **kwargs):
    """
    주요 국가 또는 항목들의 연도별 시계열 변화 추이를 비교하고 선 차트 데이터를 생성합니다.
    """
    total_rows = len(df)
    cols = [str(c) for c in df.columns]

    if not label_column or label_column not in df.columns:
        label_column = get_default_label_column(df)

    if not year_columns:
        year_columns = [c for c in cols if re.match(r"^(19|20)\d{2}$", str(c).strip())]

    if not year_columns:
        return {
            "tool": "trend_line",
            "success": False,
            "error": "시계열 분석을 위한 연도 열을 찾지 못했습니다."
        }

    available_labels = df[label_column].dropna().astype(str).tolist()

    if not items:
        default_candidates = ["Korea, Rep.", "United States", "Japan", "Germany", "World"]
        items = [c for c in default_candidates if c in available_labels]
        if not items:
            items = available_labels[:4]
    else:
        mapped_items = []
        for it in items:
            it_str = str(it).strip()
            low = it_str.lower()
            if low in ["대한민국", "한국", "korea", "south korea"]:
                m = [c for c in available_labels if "Korea, Rep" in c or "Korea" in c]
                mapped_items.append(m[0] if m else it_str)
            elif low in ["미국", "usa", "us", "united states"]:
                m = [c for c in available_labels if "United States" in c]
                mapped_items.append(m[0] if m else it_str)
            elif low in ["일본", "japan"]:
                m = [c for c in available_labels if "Japan" in c]
                mapped_items.append(m[0] if m else it_str)
            elif low in ["독일", "germany"]:
                m = [c for c in available_labels if "Germany" in c]
                mapped_items.append(m[0] if m else it_str)
            elif low in ["세계", "전세계", "world"]:
                m = [c for c in available_labels if "World" in c]
                mapped_items.append(m[0] if m else it_str)
            else:
                # partial matching in available labels
                exact = [c for c in available_labels if c.lower() == low]
                partial = [c for c in available_labels if low in c.lower()]
                if exact:
                    mapped_items.append(exact[0])
                elif partial:
                    mapped_items.append(partial[0])
                else:
                    mapped_items.append(it_str)
        items = mapped_items

    palette = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#06b6d4"]
    datasets = []
    item_summaries = []
    used_rows = 0

    for idx, item_name in enumerate(items):
        item_rows = df[df[label_column].astype(str).str.lower() == str(item_name).lower()]
        if item_rows.empty:
            continue
        used_rows += 1
        row = item_rows.iloc[0]

        values = []
        for y in year_columns:
            val = row.get(y)
            try:
                num_val = float(val) if pd.notna(val) and str(val).strip() != "" else None
            except ValueError:
                num_val = None
            values.append(sanitize_data(num_val))

        valid_nums = [v for v in values if v is not None]
        start_val = valid_nums[0] if valid_nums else None
        end_val = valid_nums[-1] if valid_nums else None
        change = round(end_val - start_val, 4) if (start_val is not None and end_val is not None) else None

        item_summaries.append({
            "item": item_name,
            "start_value": start_val,
            "end_value": end_val,
            "total_change": change
        })

        color = palette[idx % len(palette)]
        datasets.append({
            "label": str(item_name),
            "data": values,
            "borderColor": color,
            "backgroundColor": color,
            "fill": False,
            "tension": 0.2
        })

    chart_data = {
        "type": "line",
        "labels": year_columns,
        "datasets": datasets
    }

    return {
        "tool": "trend_line",
        "success": True,
        "reference_period": f"{year_columns[0]} ~ {year_columns[-1]}",
        "rows_used": used_rows,
        "rows_excluded": total_rows - used_rows,
        "exclusion_reason": f"선택 항목({len(items)}개) 외 기타 행 제외",
        "columns_used": [label_column] + year_columns,
        "unit": "% 또는 지표 수치",
        "caution": "연도별 중간 결측치가 있는 경우 선이 불연속적일 수 있으며, 시점별 지표 측정 방식 변경 여부를 유의해야 합니다.",
        "result": {
            "selected_items": items,
            "year_range": f"{year_columns[0]} ~ {year_columns[-1]}",
            "item_summaries": sanitize_data(item_summaries)
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 7. top_bottom_n (기준연도 기준 상위·하위 N - 수평 막대)
# ==============================================================================
def top_bottom_n(df: pd.DataFrame, reference_period=None, value_column=None, label_column=None, n=10, exclude_aggregates=True, highlight_target=None, **kwargs):
    """
    기준 시점을 기준으로 값이 가장 높은 상위 N개와 가장 낮은 하위 N개를 추출합니다.
    highlight_target이 전달된 경우 특정 국가(예: 대한민국)의 순위와 수치를 함께 비교합니다.
    절대 규칙: 기준 시점(reference_period)은 필수 파라미터입니다.
    """
    if not reference_period or not str(reference_period).strip():
        return {
            "tool": "top_bottom_n",
            "success": False,
            "error": "기준 시점(reference_period)은 필수 파라미터입니다. 예: '2024'"
        }

    ref_str = str(reference_period).strip()
    target_col = value_column or ref_str

    if target_col not in df.columns:
        # 연도 열들이 있는 경우 가장 최신 유효 연도 열로 안전 자동 보정
        year_cols = [c for c in df.columns if re.match(r"^(19|20)\d{2}$", str(c).strip())]
        if year_cols:
            target_col = year_cols[-1]
            ref_str = target_col
        else:
            return {
                "tool": "top_bottom_n",
                "success": False,
                "error": f"데이터셋에서 기준 열 '{target_col}'을 찾을 수 없습니다."
            }

    if not label_column or label_column not in df.columns:
        label_column = get_default_label_column(df)

    working_df = df[[label_column, target_col]].copy()
    excluded_count = 0
    excluded_reasons = []

    if exclude_aggregates:
        agg_mask = working_df[label_column].apply(lambda v: is_aggregate_row(str(v)))
        agg_count = int(agg_mask.sum())
        if agg_count > 0:
            working_df = working_df[~agg_mask]
            excluded_count += agg_count
            excluded_reasons.append(f"집계 행(대륙/소득군 등) {agg_count}개 제외")

    working_df["_numeric_val"] = pd.to_numeric(working_df[target_col], errors="coerce")
    null_mask = working_df["_numeric_val"].isna()
    null_count = int(null_mask.sum())
    if null_count > 0:
        working_df = working_df[~null_mask]
        excluded_count += null_count
        excluded_reasons.append(f"{ref_str}년도 결측 행 {null_count}개 제외")

    used_rows = len(working_df)
    if used_rows == 0:
        return {
            "tool": "top_bottom_n",
            "success": False,
            "error": f"기준 시점 '{ref_str}'에 유효한 데이터가 전혀 없습니다."
        }

    n = int(n)
    sorted_df = working_df.sort_values(by="_numeric_val", ascending=False)
    top_n_df = sorted_df.head(n)
    bottom_n_df = sorted_df.tail(n).sort_values(by="_numeric_val", ascending=True)

    top_items = [
        {"rank": i + 1, "label": str(r[label_column]), "value": round(float(r["_numeric_val"]), 4)}
        for i, (_, r) in enumerate(top_n_df.iterrows())
    ]
    bottom_items = [
        {"rank": used_rows - len(bottom_n_df) + i + 1, "label": str(r[label_column]), "value": round(float(r["_numeric_val"]), 4)}
        for i, (_, r) in enumerate(bottom_n_df.iterrows())
    ]

    # 특정 타겟(예: 대한민국) 비교 하이라이트 로직
    target_item_info = None
    if highlight_target:
        ht_str = str(highlight_target).strip().lower()
        if ht_str in ["korea", "대한민국", "한국", "korea, rep.", "south korea"]:
            target_matches = working_df[working_df[label_column].astype(str).str.contains("Korea, Rep|Korea", case=False, na=False)]
        else:
            target_matches = working_df[working_df[label_column].astype(str).str.lower().str.contains(ht_str, na=False)]

        if not target_matches.empty:
            t_row = target_matches.iloc[0]
            t_label = str(t_row[label_column])
            t_val = round(float(t_row["_numeric_val"]), 4)
            t_rank = int((sorted_df["_numeric_val"] > t_val).sum()) + 1
            target_item_info = {
                "rank": t_rank,
                "label": t_label,
                "value": t_val
            }

    chart_labels = [item["label"] for item in top_items]
    chart_values = [item["value"] for item in top_items]
    chart_colors = ["#3b82f6"] * len(top_items)  # 순위 국가들은 파랑색

    if target_item_info:
        top_labels = [item["label"] for item in top_items]
        if target_item_info["label"] in top_labels:
            idx = top_labels.index(target_item_info["label"])
            chart_colors[idx] = "#ef4444"  # 대한민국은 빨강색
        else:
            # 10등 안에 들지 않는 대한민국을 비교 항목으로 차트 끝에 추가 (빨강색)
            chart_labels.append(f"{target_item_info['label']} (대한민국, {target_item_info['rank']}위)")
            chart_values.append(target_item_info["value"])
            chart_colors.append("#ef4444")  # 대한민국은 빨강색

    chart_data = {
        "type": "bar",
        "labels": chart_labels,
        "datasets": [{
            "label": f"{ref_str}년 상위 {len(top_items)}" + (f" & {target_item_info['label']} 비교" if target_item_info else ""),
            "data": chart_values,
            "backgroundColor": chart_colors
        }]
    }

    korea_gap = None
    if target_item_info and top_items:
        korea_gap = round(top_items[0]["value"] - target_item_info["value"], 4)

    return {
        "tool": "top_bottom_n",
        "success": True,
        "reference_period": ref_str,
        "rows_used": used_rows,
        "rows_excluded": excluded_count,
        "exclusion_reason": ", ".join(excluded_reasons) if excluded_reasons else None,
        "columns_used": [label_column, target_col],
        "unit": "% (이용률 또는 해당 지표 단위)",
        "caution": f"기준 시점({ref_str})에 데이터가 없는 국가는 순위 집계에서 완전히 제외되었습니다.",
        "result": {
            "top_n": sanitize_data(top_items),
            "bottom_n": sanitize_data(bottom_items),
            "top_1": top_items[0] if top_items else None,
            "bottom_1": bottom_items[0] if bottom_items else None,
            "gap": round(top_items[0]["value"] - bottom_items[0]["value"], 4) if (top_items and bottom_items) else None,
            "korea_gap": korea_gap,
            "highlight_target": sanitize_data(target_item_info)
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 8. group_summary (그룹별 평균·합계·개수 - 막대)
# ==============================================================================
def group_summary(df: pd.DataFrame, reference_period=None, group_column=None, value_column=None, exclude_aggregates=False, **kwargs):
    """
    소득 수준이나 지역 등 그룹별 평균, 합계, 개수를 계산합니다.
    절대 규칙: 기준 시점(reference_period)은 필수 파라미터입니다.
    """
    if not reference_period or not str(reference_period).strip():
        return {
            "tool": "group_summary",
            "success": False,
            "error": "기준 시점(reference_period)은 필수 파라미터입니다. 예: '2024'"
        }

    ref_str = str(reference_period).strip()
    total_rows = len(df)
    target_col = value_column or ref_str

    if target_col not in df.columns:
        return {
            "tool": "group_summary",
            "success": False,
            "error": f"데이터셋에서 기준 열 '{target_col}'을 찾을 수 없습니다."
        }

    label_col = get_default_label_column(df)
    excluded_count = 0
    excluded_reasons = []

    if group_column and group_column in df.columns:
        working_df = df[[group_column, target_col]].copy()
        if exclude_aggregates:
            agg_mask = working_df[group_column].apply(lambda v: is_aggregate_row(str(v)))
            working_df = working_df[~agg_mask]

        working_df["_numeric_val"] = pd.to_numeric(working_df[target_col], errors="coerce")
        null_mask = working_df["_numeric_val"].isna()
        null_count = int(null_mask.sum())
        if null_count > 0:
            working_df = working_df[~null_mask]
            excluded_count += null_count
            excluded_reasons.append(f"{ref_str} 결측치 {null_count}개 제외")

        grouped = working_df.groupby(group_column)["_numeric_val"].agg(["count", "mean", "sum", "median"]).reset_index()
        group_results = [
            {
                "group": str(r[group_column]),
                "count": int(r["count"]),
                "mean": round(float(r["mean"]), 4),
                "median": round(float(r["median"]), 4),
                "sum": round(float(r["sum"]), 4)
            }
            for _, r in grouped.iterrows()
        ]
        used_rows = len(working_df)
    else:
        target_groups = [
            "High income", "Upper middle income", "Lower middle income", "Low income",
            "Europe & Central Asia", "East Asia & Pacific", "Latin America & Caribbean",
            "Sub-Saharan Africa", "Middle East & North Africa", "World"
        ]
        group_rows = []
        for tg in target_groups:
            matched = df[df[label_col].astype(str).str.lower() == tg.lower()]
            if not matched.empty:
                val = pd.to_numeric(matched.iloc[0][target_col], errors="coerce")
                if pd.notna(val):
                    group_rows.append({
                        "group": tg,
                        "value": round(float(val), 4),
                        "count": 1
                    })

        used_rows = len(group_rows)
        excluded_count = total_rows - used_rows
        excluded_reasons.append(f"지정된 소득군/지역 집계 행({used_rows}개) 외 개별 국가 행 제외")
        group_results = group_rows

    if not group_results:
        return {
            "tool": "group_summary",
            "success": False,
            "error": f"기준 시점 '{ref_str}'에 분석 가능한 그룹 데이터를 찾지 못했습니다."
        }

    labels = [g["group"] for g in group_results]
    values = [g.get("mean") or g.get("value") for g in group_results]
    chart_data = {
        "type": "bar",
        "labels": labels,
        "datasets": [{
            "label": f"{ref_str}년 그룹별 수치",
            "data": values,
            "backgroundColor": "#10b981"
        }]
    }

    return {
        "tool": "group_summary",
        "success": True,
        "reference_period": ref_str,
        "rows_used": used_rows,
        "rows_excluded": excluded_count,
        "exclusion_reason": ", ".join(excluded_reasons) if excluded_reasons else None,
        "columns_used": [group_column or label_col, target_col],
        "unit": "% 또는 그룹별 지표",
        "caution": "그룹 간 단순 평균 비교 시 각 그룹에 속한 국가 수나 인구 가중치가 반영되었는지 확인해야 합니다.",
        "result": {
            "group_count": len(group_results),
            "summary": sanitize_data(group_results)
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 9. change_rate (두 시점 사이 변화량·변화율 - 막대)
# ==============================================================================
def change_rate(df: pd.DataFrame, reference_period=None, base_period=None, label_column=None, n=10, exclude_aggregates=True, **kwargs):
    """
    두 시점(예: 2014년 vs 2024년) 사이의 증가량과 증가율을 계산하고 급성장 항목을 추출합니다.
    절대 규칙: 기준 시점(reference_period)은 필수 파라미터입니다.
    """
    if not reference_period or not str(reference_period).strip():
        return {
            "tool": "change_rate",
            "success": False,
            "error": "기준 시점(reference_period)은 필수 파라미터입니다. 예: '2024'"
        }

    ref_str = str(reference_period).strip()
    cols = [str(c) for c in df.columns]

    if ref_str not in cols:
        return {
            "tool": "change_rate",
            "success": False,
            "error": f"데이터셋에서 기준 열 '{ref_str}'을 찾을 수 없습니다."
        }

    if not label_column or label_column not in df.columns:
        label_column = get_default_label_column(df)

    # 비교 기준 시점(base_period) 자동 결정 (지정 없으면 10년 전 또는 5년 전)
    if not base_period:
        try:
            ref_int = int(ref_str)
            target_base = str(ref_int - 10)
            if target_base in cols:
                base_period = target_base
            else:
                target_base_5 = str(ref_int - 5)
                base_period = target_base_5 if target_base_5 in cols else None
        except ValueError:
            pass

    if not base_period or str(base_period) not in cols:
        year_cols = [c for c in cols if re.match(r"^(19|20)\d{2}$", str(c).strip())]
        if year_cols and ref_str in year_cols:
            idx = year_cols.index(ref_str)
            base_period = year_cols[max(0, idx - 10)]
        else:
            return {
                "tool": "change_rate",
                "success": False,
                "error": "비교할 이전 시점(base_period)을 찾지 못했습니다."
            }

    base_str = str(base_period)
    working_df = df[[label_column, base_str, ref_str]].copy()
    excluded_count = 0
    excluded_reasons = []

    if exclude_aggregates:
        agg_mask = working_df[label_column].apply(lambda v: is_aggregate_row(str(v)))
        agg_count = int(agg_mask.sum())
        if agg_count > 0:
            working_df = working_df[~agg_mask]
            excluded_count += agg_count
            excluded_reasons.append(f"집계 행 {agg_count}개 제외")

    working_df["_base_num"] = pd.to_numeric(working_df[base_str], errors="coerce")
    working_df["_ref_num"] = pd.to_numeric(working_df[ref_str], errors="coerce")

    # 두 시점 중 하나라도 결측인 행 제외
    null_mask = working_df["_base_num"].isna() | working_df["_ref_num"].isna()
    null_count = int(null_mask.sum())
    if null_count > 0:
        working_df = working_df[~null_mask]
        excluded_count += null_count
        excluded_reasons.append(f"시점별 결측치 행 {null_count}개 제외")

    used_rows = len(working_df)
    if used_rows == 0:
        return {
            "tool": "change_rate",
            "success": False,
            "error": f"비교 구간({base_str} ~ {ref_str})에 양쪽 모두 유효한 데이터가 없습니다."
        }

    # 변화량(diff)과 변화율(pct_change) 계산
    working_df["_diff"] = working_df["_ref_num"] - working_df["_base_num"]
    # 0으로 나누기 방어
    working_df["_pct_change"] = working_df.apply(
        lambda r: ((r["_diff"] / r["_base_num"]) * 100) if r["_base_num"] > 0 else (100.0 if r["_diff"] > 0 else 0.0),
        axis=1
    )

    n = int(n)
    top_diff_df = working_df.sort_values(by="_diff", ascending=False).head(n)

    top_growth_items = [
        {
            "rank": i + 1,
            "label": str(r[label_column]),
            "base_val": round(float(r["_base_num"]), 4),
            "ref_val": round(float(r["_ref_num"]), 4),
            "diff": round(float(r["_diff"]), 4),
            "pct_change": round(float(r["_pct_change"]), 2)
        }
        for i, (_, r) in enumerate(top_diff_df.iterrows())
    ]

    chart_data = {
        "type": "bar",
        "labels": [item["label"] for item in top_growth_items],
        "datasets": [{
            "label": f"{base_str}대비 {ref_str} 증가량(%p)",
            "data": [item["diff"] for item in top_growth_items],
            "backgroundColor": "#f59e0b"
        }]
    }

    return {
        "tool": "change_rate",
        "success": True,
        "reference_period": f"{base_str} ~ {ref_str}",
        "rows_used": used_rows,
        "rows_excluded": excluded_count,
        "exclusion_reason": ", ".join(excluded_reasons) if excluded_reasons else None,
        "columns_used": [label_column, base_str, ref_str],
        "unit": "%p (퍼센트포인트 증가량) / % (증가율)",
        "caution": f"기저 효과(시작 시점 {base_str}년 수치가 매우 낮은 경우 변화율이 과도하게 높게 나타날 수 있음)에 유의하세요.",
        "result": {
            "base_period": base_str,
            "reference_period": ref_str,
            "top_growers": sanitize_data(top_growth_items),
            "avg_diff": round(float(working_df["_diff"].mean()), 4),
            "median_diff": round(float(working_df["_diff"].median()), 4)
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 10. distribution (구간별 분포 - 히스토그램)
# ==============================================================================
def distribution(df: pd.DataFrame, reference_period=None, value_column=None, bins=5, exclude_aggregates=True, **kwargs):
    """
    기준 시점 데이터의 구간별 빈도(히스토그램)와 분포 특성을 계산합니다.
    절대 규칙: 기준 시점(reference_period)은 필수 파라미터입니다.
    """
    if not reference_period or not str(reference_period).strip():
        return {
            "tool": "distribution",
            "success": False,
            "error": "기준 시점(reference_period)은 필수 파라미터입니다. 예: '2024'"
        }

    ref_str = str(reference_period).strip()
    target_col = value_column or ref_str

    if target_col not in df.columns:
        return {
            "tool": "distribution",
            "success": False,
            "error": f"데이터셋에서 기준 열 '{target_col}'을 찾을 수 없습니다."
        }

    label_col = get_default_label_column(df)
    working_df = df.copy()
    excluded_count = 0
    excluded_reasons = []

    if exclude_aggregates:
        agg_mask = working_df[label_col].apply(lambda v: is_aggregate_row(str(v)))
        agg_count = int(agg_mask.sum())
        if agg_count > 0:
            working_df = working_df[~agg_mask]
            excluded_count += agg_count
            excluded_reasons.append(f"집계 행 {agg_count}개 제외")

    series = pd.to_numeric(working_df[target_col], errors="coerce").dropna()
    null_count = len(working_df) - len(series)
    if null_count > 0:
        excluded_count += null_count
        excluded_reasons.append(f"{ref_str} 결측치 {null_count}개 제외")

    used_rows = len(series)
    if used_rows == 0:
        return {
            "tool": "distribution",
            "success": False,
            "error": f"기준 시점 '{ref_str}'에 유효한 데이터가 없습니다."
        }

    bins = int(bins)
    # 0~100 범위의 백분율 지표인 경우 균등 5개 구간(0-20, 20-40, ...) 생성
    if series.min() >= 0 and series.max() <= 100:
        bin_edges = [0, 20, 40, 60, 80, 100]
        bin_labels = ["0~20%", "20~40%", "40~60%", "60~80%", "80~100%"]
    else:
        # 일반 수치형인 경우 pandas cut 구간
        cuts, bin_edges = pd.cut(series, bins=bins, retbins=True)
        bin_labels = [f"{round(bin_edges[i], 1)}~{round(bin_edges[i+1], 1)}" for i in range(len(bin_edges)-1)]

    cut_series = pd.cut(series, bins=bin_edges, labels=bin_labels, include_lowest=True)
    counts = cut_series.value_counts(sort=False)

    dist_items = [
        {
            "bin": str(label),
            "count": int(counts.get(label, 0)),
            "ratio": round(float(counts.get(label, 0) / used_rows), 4)
        }
        for label in bin_labels
    ]

    chart_data = {
        "type": "bar",
        "labels": bin_labels,
        "datasets": [{
            "label": f"{ref_str}년 구간별 분포 (국가 수)",
            "data": [item["count"] for item in dist_items],
            "backgroundColor": "#8b5cf6"
        }]
    }

    return {
        "tool": "distribution",
        "success": True,
        "reference_period": ref_str,
        "rows_used": used_rows,
        "rows_excluded": excluded_count,
        "exclusion_reason": ", ".join(excluded_reasons) if excluded_reasons else None,
        "columns_used": [target_col],
        "unit": "개국 (빈도수) / %",
        "caution": "특정 구간에 데이터가 과도하게 몰려 있는 경우(비대칭 분포) 단순 산술평균보다 중위수가 대표성을 가집니다.",
        "result": {
            "total_count": used_rows,
            "bins_count": len(bin_labels),
            "distribution": sanitize_data(dist_items),
            "mean": round(float(series.mean()), 4),
            "median": round(float(series.median()), 4)
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 11. correlation_scatter (두 숫자 열 상관계수 - 산점도)
# ==============================================================================
def correlation_scatter(df: pd.DataFrame, reference_period=None, col1=None, col2=None, exclude_aggregates=True, **kwargs):
    """
    두 시점 또는 두 지표 간의 피어슨 상관계수를 계산하고 산점도 데이터를 생성합니다.
    절대 규칙: 기준 시점(reference_period)은 필수 파라미터이며,
    상관계수 계산 시 반드시 '상관관계는 인과관계가 아니다'를 주의사항에 명시합니다.
    """
    if not reference_period or not str(reference_period).strip():
        return {
            "tool": "correlation_scatter",
            "success": False,
            "error": "기준 시점(reference_period)은 필수 파라미터입니다. 예: '2024'"
        }

    ref_str = str(reference_period).strip()
    cols = [str(c) for c in df.columns]

    if not col2:
        col2 = ref_str

    if not col1:
        # 기본 비교열로 10년 전 연도 열 탐색
        try:
            ref_int = int(ref_str)
            target_10 = str(ref_int - 10)
            col1 = target_10 if target_10 in cols else None
        except ValueError:
            pass

    if not col1 or col1 not in cols or col2 not in cols:
        num_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) or re.match(r"^(19|20)\d{2}$", str(c))]
        if len(num_cols) >= 2:
            col1, col2 = num_cols[-2], num_cols[-1]
        else:
            return {
                "tool": "correlation_scatter",
                "success": False,
                "error": "상관분석을 수행할 두 개의 유효한 숫자 열을 찾지 못했습니다."
            }

    label_col = get_default_label_column(df)
    working_df = df[[label_col, col1, col2]].copy()
    excluded_count = 0
    excluded_reasons = []

    if exclude_aggregates:
        agg_mask = working_df[label_col].apply(lambda v: is_aggregate_row(str(v)))
        agg_count = int(agg_mask.sum())
        if agg_count > 0:
            working_df = working_df[~agg_mask]
            excluded_count += agg_count
            excluded_reasons.append(f"집계 행 {agg_count}개 제외")

    working_df["_x"] = pd.to_numeric(working_df[col1], errors="coerce")
    working_df["_y"] = pd.to_numeric(working_df[col2], errors="coerce")

    clean_df = working_df.dropna(subset=["_x", "_y"])
    null_count = len(working_df) - len(clean_df)
    if null_count > 0:
        excluded_count += null_count
        excluded_reasons.append(f"결측치 행 {null_count}개 제외")

    used_rows = len(clean_df)
    if used_rows < 3:
        return {
            "tool": "correlation_scatter",
            "success": False,
            "error": "상관계수를 산출하기 위한 유효 데이터 쌍이 최소 3개 이상 필요합니다."
        }

    corr_val = float(clean_df["_x"].corr(clean_df["_y"]))

    scatter_points = [
        {
            "x": round(float(r["_x"]), 4),
            "y": round(float(r["_y"]), 4),
            "label": str(r[label_col])
        }
        for _, r in clean_df.iterrows()
    ]

    chart_data = {
        "type": "scatter",
        "datasets": [{
            "label": f"{col1} vs {col2}",
            "data": scatter_points,
            "backgroundColor": "#0284c7"
        }]
    }

    return {
        "tool": "correlation_scatter",
        "success": True,
        "reference_period": f"{col1} & {col2}",
        "rows_used": used_rows,
        "rows_excluded": excluded_count,
        "exclusion_reason": ", ".join(excluded_reasons) if excluded_reasons else None,
        "columns_used": [col1, col2],
        "unit": "피어슨 상관계수 (r)",
        "caution": "주의: 상관관계는 인과관계가 아닙니다. 두 변수가 강한 통계적 연관성을 보이더라도 한쪽이 다른 쪽의 원인임을 의미하지 않습니다.",
        "result": {
            "col_x": col1,
            "col_y": col2,
            "correlation_coefficient": round(corr_val, 4),
            "sample_size": used_rows
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 12. compare_one_vs_all (특정 항목 vs 전체 평균·중앙값 - 강조 막대)
# ==============================================================================
def compare_one_vs_all(df: pd.DataFrame, reference_period=None, target_item=None, label_column=None, value_column=None, exclude_aggregates=True, **kwargs):
    """
    특정 항목(예: 한국 Korea, Rep.)의 수치를 전체 평균 및 중앙값과 직관적으로 비교합니다.
    절대 규칙: 기준 시점(reference_period)은 필수 파라미터입니다.
    """
    if not reference_period or not str(reference_period).strip():
        return {
            "tool": "compare_one_vs_all",
            "success": False,
            "error": "기준 시점(reference_period)은 필수 파라미터입니다. 예: '2024'"
        }

    ref_str = str(reference_period).strip()
    target_col = value_column or ref_str

    if target_col not in df.columns:
        return {
            "tool": "compare_one_vs_all",
            "success": False,
            "error": f"데이터셋에서 기준 열 '{target_col}'을 찾을 수 없습니다."
        }

    if not label_column or label_column not in df.columns:
        label_column = get_default_label_column(df)

    working_df = df[[label_column, target_col]].copy()
    excluded_count = 0
    excluded_reasons = []

    # 타겟 항목 기본값 자동 지정 및 별칭 매핑
    if not target_item:
        korea_rows = working_df[working_df[label_column].astype(str).str.contains("Korea, Rep|Korea", case=False, na=False)]
        if not korea_rows.empty:
            target_item = str(korea_rows.iloc[0][label_column])
        else:
            target_item = str(working_df.iloc[0][label_column])
    else:
        t_low = str(target_item).strip().lower()
        if t_low in ["대한민국", "한국", "korea", "south korea"]:
            korea_rows = working_df[working_df[label_column].astype(str).str.contains("Korea, Rep|Korea", case=False, na=False)]
            if not korea_rows.empty:
                target_item = str(korea_rows.iloc[0][label_column])
        elif t_low in ["미국", "united states", "usa"]:
            us_rows = working_df[working_df[label_column].astype(str).str.contains("United States", case=False, na=False)]
            if not us_rows.empty:
                target_item = str(us_rows.iloc[0][label_column])
        elif t_low in ["일본", "japan"]:
            jp_rows = working_df[working_df[label_column].astype(str).str.contains("Japan", case=False, na=False)]
            if not jp_rows.empty:
                target_item = str(jp_rows.iloc[0][label_column])

    # 타겟 항목 행 탐색
    matched_target = working_df[working_df[label_column].astype(str).str.lower() == str(target_item).lower()]
    if matched_target.empty:
        # 부분 일치 검색
        matched_target = working_df[working_df[label_column].astype(str).str.lower().str.contains(str(target_item).lower(), na=False)]
    if matched_target.empty:
        return {
            "tool": "compare_one_vs_all",
            "success": False,
            "error": f"데이터셋에서 대상 항목 '{target_item}'을 찾을 수 없습니다."
        }

    target_raw_val = pd.to_numeric(matched_target.iloc[0][target_col], errors="coerce")
    if pd.isna(target_raw_val):
        return {
            "tool": "compare_one_vs_all",
            "success": False,
            "error": f"대상 항목 '{target_item}'의 {ref_str}년 데이터가 결측되어 비교할 수 없습니다."
        }
    target_val = float(target_raw_val)

    # 전체 그룹 집계 시 집계 행 제외
    if exclude_aggregates:
        agg_mask = working_df[label_column].apply(lambda v: is_aggregate_row(str(v)))
        agg_count = int(agg_mask.sum())
        if agg_count > 0:
            working_df = working_df[~agg_mask]
            excluded_count += agg_count
            excluded_reasons.append(f"집계 행 {agg_count}개 제외")

    working_df["_num"] = pd.to_numeric(working_df[target_col], errors="coerce")
    valid_series = working_df["_num"].dropna()
    null_count = len(working_df) - len(valid_series)
    if null_count > 0:
        excluded_count += null_count
        excluded_reasons.append(f"{ref_str} 결측치 {null_count}개 제외")

    used_rows = len(valid_series)
    mean_val = float(valid_series.mean())
    median_val = float(valid_series.median())

    # 타겟의 순위 계산
    rank = int((valid_series > target_val).sum() + 1)
    percentile = round(float((1 - (rank / used_rows)) * 100), 2) if used_rows > 0 else 0.0

    # 강조 막대 차트 데이터
    chart_data = {
        "type": "bar",
        "labels": [str(target_item), "전체 평균", "전체 중앙값"],
        "datasets": [{
            "label": f"{ref_str}년 비교 수치",
            "data": [round(target_val, 4), round(mean_val, 4), round(median_val, 4)],
            "backgroundColor": ["#ef4444", "#94a3b8", "#64748b"]
        }]
    }

    return {
        "tool": "compare_one_vs_all",
        "success": True,
        "reference_period": ref_str,
        "rows_used": used_rows,
        "rows_excluded": excluded_count,
        "exclusion_reason": ", ".join(excluded_reasons) if excluded_reasons else None,
        "columns_used": [label_column, target_col],
        "unit": "% 또는 지표 수치 단위",
        "caution": f"{target_item}의 수치를 비교할 때 제외된 결측 국가와 집계 행이 전체 평균에 미친 영향을 고려해야 합니다.",
        "result": {
            "target_item": target_item,
            "target_value": round(target_val, 4),
            "group_mean": round(mean_val, 4),
            "group_median": round(median_val, 4),
            "diff_from_mean": round(target_val - mean_val, 4),
            "diff_from_median": round(target_val - median_val, 4),
            "rank": rank,
            "total_evaluated_countries": used_rows,
            "percentile": percentile
        },
        "chart_data": chart_data
    }


# ==============================================================================
# 도구 카탈로그 메타데이터 (Gemini /suggest 및 /run 검증용)
# ==============================================================================
TOOL_CATALOG = {
    "reshape_wide_to_long": {
        "name": "reshape_wide_to_long",
        "description": "연도 열들을 행으로 접어 시계열 포맷으로 변환합니다.",
        "params": ["id_vars", "value_name", "var_name"],
        "requires_reference_period": False
    },
    "quality_report": {
        "name": "quality_report",
        "description": "결측·중복·데이터타입·이상한 열 이름을 정밀 진단합니다.",
        "params": [],
        "requires_reference_period": False
    },
    "year_coverage": {
        "name": "year_coverage",
        "description": "연도별 값 개수 충실도와 권장 기준연도를 계산합니다.",
        "params": [],
        "requires_reference_period": False
    },
    "detect_aggregates": {
        "name": "detect_aggregates",
        "description": "대륙, 소득군, 세계 합계 등 집계 행 후보를 탐지합니다.",
        "params": ["label_column"],
        "requires_reference_period": False
    },
    "describe_numeric": {
        "name": "describe_numeric",
        "description": "개수, 평균, 중앙값, 최소, 최대, 표준편차 등 기술통계량을 산출합니다.",
        "params": ["value_column", "reference_period", "exclude_aggregates"],
        "requires_reference_period": False
    },
    "trend_line": {
        "name": "trend_line",
        "description": "선택 항목들의 연도별 시계열 변화 추이를 선 차트로 시각화합니다.",
        "params": ["items", "label_column", "year_columns"],
        "requires_reference_period": False
    },
    "top_bottom_n": {
        "name": "top_bottom_n",
        "description": "기준연도 기준 상위 N개와 하위 N개를 수평 막대 차트로 비교합니다.",
        "params": ["reference_period", "value_column", "label_column", "n", "exclude_aggregates"],
        "requires_reference_period": True
    },
    "group_summary": {
        "name": "group_summary",
        "description": "소득군 또는 지역 등 그룹별 평균, 합계, 개수를 계산합니다.",
        "params": ["reference_period", "group_column", "value_column", "exclude_aggregates"],
        "requires_reference_period": True
    },
    "change_rate": {
        "name": "change_rate",
        "description": "두 시점 사이의 증가량과 증가율을 계산하여 급성장 항목을 추출합니다.",
        "params": ["reference_period", "base_period", "label_column", "n", "exclude_aggregates"],
        "requires_reference_period": True
    },
    "distribution": {
        "name": "distribution",
        "description": "기준 시점 데이터의 구간별 분포(히스토그램)와 빈도를 계산합니다.",
        "params": ["reference_period", "value_column", "bins", "exclude_aggregates"],
        "requires_reference_period": True
    },
    "correlation_scatter": {
        "name": "correlation_scatter",
        "description": "두 시점 또는 지표 간 상관계수를 계산하고 산점도를 생성합니다. (상관관계!=인과관계)",
        "params": ["reference_period", "col1", "col2", "exclude_aggregates"],
        "requires_reference_period": True
    },
    "compare_one_vs_all": {
        "name": "compare_one_vs_all",
        "description": "특정 항목을 전체 평균 및 중앙값과 강조 막대로 비교합니다.",
        "params": ["reference_period", "target_item", "label_column", "value_column", "exclude_aggregates"],
        "requires_reference_period": True
    }
}
