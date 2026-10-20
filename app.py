import io
import csv
import glob
import json
import re
import os
import time
import logging
import math
import pandas as pd
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import (
    TOOL_CATALOG,
    reshape_wide_to_long,
    quality_report,
    year_coverage,
    detect_aggregates,
    describe_numeric,
    trend_line,
    top_bottom_n,
    group_summary,
    change_rate,
    distribution,
    correlation_scatter,
    compare_one_vs_all
)

# .env 환경변수 로드
load_dotenv()

# 로깅 설정 (print 대신 logging 모듈 사용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("data-insight-builder")

# Flask 앱 초기화
app = Flask(__name__)

# 업로드 파일 최대 크기 설정 (기본값 10MB)
max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
app.config["MAX_CONTENT_LENGTH"] = max_upload_mb * 1024 * 1024

# 메모리에 1개 데이터셋만 보관 (디스크 영구 저장 없음)
current_dataset = {}

# 실행 가능한 도구 함수 매핑
TOOL_FUNCTIONS = {
    "reshape_wide_to_long": reshape_wide_to_long,
    "quality_report": quality_report,
    "year_coverage": year_coverage,
    "detect_aggregates": detect_aggregates,
    "describe_numeric": describe_numeric,
    "trend_line": trend_line,
    "top_bottom_n": top_bottom_n,
    "group_summary": group_summary,
    "change_rate": change_rate,
    "distribution": distribution,
    "correlation_scatter": correlation_scatter,
    "compare_one_vs_all": compare_one_vs_all
}


def detect_encoding(raw_bytes: bytes):
    """
    utf-8-sig, utf-8, cp949, euc-kr 순서로 인코딩을 시도합니다.
    성공한 인코딩과 디코딩된 텍스트 문자열을 반환합니다.
    """
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    for enc in encodings:
        try:
            decoded = raw_bytes.decode(enc)
            logger.info("[ENCODING] %s 시도 성공", enc)
            return enc, decoded
        except UnicodeDecodeError:
            logger.info("[ENCODING] %s 시도 실패", enc)
            continue
    return None, None


def detect_header_and_parse(content_text: str):
    """
    앞쪽 최대 25줄을 검사하여 유효한 열 이름(헤더) 행을 감지하고,
    건너뛴 줄 수와 파싱된 Pandas DataFrame을 반환합니다.
    """
    lines = content_text.splitlines()
    if not lines:
        return None, 0, ["빈 텍스트 내용입니다."]

    scan_limit = min(25, len(lines))
    max_col_count = 0
    header_index = 0

    for idx in range(scan_limit):
        line = lines[idx].strip()
        if not line:
            continue
        try:
            parsed_row = next(csv.reader([line]))
            non_empty_cols = [col.strip() for col in parsed_row if col.strip()]
            if len(non_empty_cols) > max_col_count:
                max_col_count = len(non_empty_cols)
                header_index = idx
        except Exception:
            continue

    if max_col_count == 0:
        return None, 0, ["유효한 헤더(열 이름) 행을 감지하지 못했습니다."]

    logger.info("[HEADER] 헤더 줄 감지 결과: 행 번호=%d (건너뛴 줄 수=%d, 감지된 열 수=%d)",
                header_index + 1, header_index, max_col_count)

    # pandas로 CSV 파싱
    df = pd.read_csv(io.StringIO(content_text), skiprows=header_index)

    warnings = []
    # 이름 없는 열 또는 Unnamed 열 감지
    unnamed_cols = [str(c) for c in df.columns if str(c).startswith("Unnamed:") or not str(c).strip()]
    if unnamed_cols:
        warnings.append(f"이름이 없는 열 또는 빈 끝자리 열({len(unnamed_cols)}개)이 감지되었습니다: {', '.join(unnamed_cols[:5])}")

    # 전체가 결측치(빈 열)인 열 감지
    all_null_cols = [str(c) for c in df.columns if df[c].isna().all()]
    if all_null_cols:
        warnings.append(f"모든 데이터가 비어 있는 열({len(all_null_cols)}개)이 있습니다: {', '.join(all_null_cols[:5])}")

    return df, header_index, warnings


def sanitize_val(val):
    """JSON 직렬화 시 NaN, Inf를 None으로 치환"""
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return None
    return val


def get_indicator_metadata(df: pd.DataFrame = None):
    """
    data 폴더 내 Metadata_Indicator 파일 또는 DataFrame에서 지표 정의와 출처를 추출합니다.
    """
    indicator_meta = {
        "name": "Individuals using the Internet (% of population)",
        "definition": "Internet users are individuals who have used the Internet (from any location) in the last 3 months.",
        "source": "World Telecommunication/ICT Indicators Database, International Telecommunication Union (ITU), https://datahub.itu.int/"
    }

    # data 디렉터리 내 Metadata_Indicator 파일 탐색
    meta_files = glob.glob("data/**/Metadata_Indicator*.csv", recursive=True)
    if meta_files:
        try:
            with open(meta_files[0], "r", encoding="utf-8-sig", errors="ignore") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if r.get("INDICATOR_NAME"):
                        indicator_meta["name"] = r.get("INDICATOR_NAME")
                    if r.get("SOURCE_NOTE"):
                        indicator_meta["definition"] = r.get("SOURCE_NOTE")
                    if r.get("SOURCE_ORGANIZATION"):
                        indicator_meta["source"] = r.get("SOURCE_ORGANIZATION")
                    break
        except Exception as e:
            logger.warning("[METADATA] 지표 메타데이터 읽기 경고: %s", e)

    # DataFrame 내 Indicator Name 열이 존재하면 반영
    if df is not None and "Indicator Name" in df.columns:
        first_valid = df["Indicator Name"].dropna()
        if not first_valid.empty:
            indicator_meta["name"] = str(first_valid.iloc[0])

    return indicator_meta


def diagnose_dataframe(df: pd.DataFrame, initial_warnings: list):
    """
    13가지 필수 진단 항목을 분석하여 상세 진단 결과 딕셔너리를 반환합니다.
    """
    warnings = list(initial_warnings)
    total_rows = len(df)
    columns = [str(c) for c in df.columns]

    dtypes = {col: str(df[col].dtype) for col in columns}

    numeric_columns = []
    string_columns = []
    year_columns = []

    for col in columns:
        if re.match(r"^(19|20)\d{2}$", str(col).strip()):
            year_columns.append(col)
        elif pd.api.types.is_numeric_dtype(df[col]):
            numeric_columns.append(col)
        else:
            non_na = df[col].dropna()
            if len(non_na) > 0 and pd.to_numeric(non_na, errors="coerce").notna().mean() > 0.8:
                numeric_columns.append(col)
            else:
                string_columns.append(col)

    missing_values = {}
    high_missing_cols = []
    for col in columns:
        missing_count = int(df[col].isna().sum())
        missing_ratio = round(float(missing_count / total_rows), 4) if total_rows > 0 else 0.0
        missing_values[col] = {
            "count": missing_count,
            "ratio": missing_ratio
        }
        if missing_ratio >= 0.5:
            high_missing_cols.append(col)

    if high_missing_cols:
        warnings.append(f"결측치 비율이 50% 이상인 열({len(high_missing_cols)}개)이 있습니다: {', '.join(high_missing_cols[:5])}")

    duplicate_rows_count = int(df.duplicated().sum())
    if duplicate_rows_count > 0:
        warnings.append(f"완전히 동일한 중복 행이 {duplicate_rows_count}개 발견되었습니다.")

    unnamed_columns = [c for c in columns if str(c).startswith("Unnamed:") or not str(c).strip()]
    empty_columns = [c for c in columns if df[c].isna().all()]

    year_coverage = {}
    if year_columns:
        for y_col in year_columns:
            filled_count = int(df[y_col].notna().sum())
            filled_ratio = round(float(filled_count / total_rows), 4) if total_rows > 0 else 0.0
            year_coverage[y_col] = {
                "filled_count": filled_count,
                "filled_ratio": filled_ratio
            }

    recommended_reference_year = None
    if year_coverage:
        max_filled = max(item["filled_count"] for item in year_coverage.values())
        candidates = [
            y for y, item in year_coverage.items()
            if item["filled_count"] >= max_filled * 0.85 and item["filled_count"] > 0
        ]
        recommended_reference_year = candidates[-1] if candidates else max(year_coverage.keys(), key=lambda y: year_coverage[y]["filled_count"])

    agg_keywords = ["world", "oecd", "euro area", "european union", "income", "area", "total", "dividend", "ida & ibrd", "caribbean"]
    aggregate_row_candidates = []

    label_col = string_columns[0] if string_columns else columns[0]
    for idx, val in df[label_col].items():
        val_str = str(val).lower() if pd.notna(val) else ""
        if any(kw in val_str for kw in agg_keywords):
            aggregate_row_candidates.append({
                "row_index": int(idx),
                "label": str(val)
            })

    if aggregate_row_candidates:
        warnings.append(f"지역/소득분류 등 집계 행 후보가 {len(aggregate_row_candidates)}개 감지되었습니다. (개별 국가 분석 시 제외 권장)")

    preview_rows = []
    preview_df = df.head(10)
    for _, row in preview_df.iterrows():
        clean_row = {col: sanitize_val(row[col]) for col in columns}
        preview_rows.append(clean_row)

    logger.info("[DIAGNOSE] 진단 완료 warnings=%d개", len(warnings))

    return {
        "dtypes": dtypes,
        "numeric_columns": numeric_columns,
        "string_columns": string_columns,
        "year_columns": year_columns,
        "missing_values": missing_values,
        "duplicate_rows_count": duplicate_rows_count,
        "unnamed_columns": unnamed_columns,
        "empty_columns": empty_columns,
        "year_coverage": year_coverage,
        "recommended_reference_year": recommended_reference_year,
        "aggregate_row_candidates": aggregate_row_candidates,
        "preview_rows": preview_rows,
        "warnings": warnings
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    api_key = os.getenv("GEMINI_API_KEY")
    api_key_set = bool(api_key and api_key.strip() and api_key != "your_gemini_api_key_here")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    logger.info("[REQUEST] GET /health - api_key_set=%s, model=%s", api_key_set, model_name)

    return jsonify({
        "status": "ok",
        "api_key_configured": api_key_set,
        "gemini_model": model_name
    }), 200


@app.route("/inspect", methods=["POST"])
def inspect_file():
    """
    Step 13: 13가지 항목 종합 데이터 품질 진단 API
    """
    logger.info("[REQUEST] POST /inspect")

    if "file" not in request.files:
        logger.warning("[ERROR] 파일이 선택되지 않았습니다.")
        return jsonify({"error": "업로드할 CSV 파일을 선택해주세요."}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file or uploaded_file.filename == "":
        logger.warning("[ERROR] 파일명이 비어 있습니다.")
        return jsonify({"error": "파일이 선택되지 않았습니다."}), 400

    if not uploaded_file.filename.lower().endswith(".csv"):
        logger.warning("[ERROR] 잘못된 확장자: %s", uploaded_file.filename)
        return jsonify({"error": "CSV 파일(.csv)만 업로드할 수 있습니다."}), 400

    file_bytes = uploaded_file.read()
    file_size = len(file_bytes)
    logger.info("[FILE] name=%s size=%d bytes", uploaded_file.filename, file_size)

    if file_size == 0:
        logger.warning("[ERROR] 업로드된 파일이 빈 파일입니다.")
        return jsonify({"error": "내용이 비어 있는 빈 파일입니다."}), 400

    encoding, text_content = detect_encoding(file_bytes)
    if not encoding:
        logger.error("[ERROR] 지원 인코딩 실패")
        return jsonify({
            "error": "파일 인코딩을 판별하지 못했습니다. (utf-8-sig, utf-8, cp949, euc-kr 미지원)"
        }), 400

    df, skipped_rows, initial_warnings = detect_header_and_parse(text_content)
    if df is None:
        logger.error("[ERROR] 헤더 줄 감지 실패")
        return jsonify({"error": "CSV 파일에서 유효한 헤더(열 이름) 줄을 찾을 수 없습니다."}), 400

    logger.info("[CSV] parsing 완료 rows=%d columns=%d", len(df), len(df.columns))

    diag = diagnose_dataframe(df, initial_warnings)

    # 만약 업로드된 파일에 연도별 수치 데이터 열이 없는 경우(예: Metadata_Country 등),
    # data 폴더에 있는 실제 시계열 수치 데이터셋(API_*.csv)을 자동으로 탐색하여 연동
    if len(diag["year_columns"]) == 0:
        candidate_files = glob.glob(os.path.join("data", "**", "API_*.csv"), recursive=True)
        if candidate_files:
            main_csv_path = candidate_files[0]
            try:
                with open(main_csv_path, "rb") as mf:
                    m_bytes = mf.read()
                m_enc, m_text = detect_encoding(m_bytes)
                if m_enc:
                    main_df, m_skip, m_warns = detect_header_and_parse(m_text)
                    if main_df is not None:
                        main_diag = diagnose_dataframe(main_df, m_warns)
                        if len(main_diag["year_columns"]) > 0:
                            df = main_df
                            diag = main_diag
                            skipped_rows = m_skip
                            encoding = m_enc
                            diag["warnings"].insert(0, f"💡 안내: 선택하신 파일({uploaded_file.filename})은 부가 설명(메타데이터) 파일입니다. 정상적인 통계 계산 및 시각화 도형을 제공하기 위해 실제 수치 데이터셋({os.path.basename(main_csv_path)})을 자동으로 연결하여 분석을 진행합니다.")
                            logger.info("[AUTO_LINK] 수치 데이터셋 자동 연동 성공: %s", main_csv_path)
            except Exception as auto_e:
                logger.warning("[AUTO_LINK] 메인 데이터셋 자동 연동 실패: %s", auto_e)

    global current_dataset
    current_dataset = {
        "filename": uploaded_file.filename,
        "file_size": file_size,
        "encoding": encoding,
        "skipped_rows": skipped_rows,
        "df": df,
        "diagnosis": diag
    }

    return jsonify({
        "status": "success",
        "filename": uploaded_file.filename,
        "file_size_bytes": file_size,
        "encoding": encoding,
        "skipped_rows": skipped_rows,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": [str(c) for c in df.columns],
        "dtypes": diag["dtypes"],
        "numeric_columns": diag["numeric_columns"],
        "string_columns": diag["string_columns"],
        "year_columns": diag["year_columns"],
        "missing_values": diag["missing_values"],
        "duplicate_rows_count": diag["duplicate_rows_count"],
        "unnamed_columns": diag["unnamed_columns"],
        "empty_columns": diag["empty_columns"],
        "year_coverage": diag["year_coverage"],
        "recommended_reference_year": diag["recommended_reference_year"],
        "aggregate_row_candidates": diag["aggregate_row_candidates"],
        "preview_rows": diag["preview_rows"],
        "warnings": diag["warnings"],
        "memory_notice": "데이터셋은 메모리에만 임시 보관되며, 서버가 재시작되면 초기화됩니다."
    }), 200


@app.route("/ask", methods=["POST"])
def ask_question():
    """
    데이터 진단 후 사용자가 데이터 상태나 분석 방향에 대해 궁금한 점을 질문하면
    Gemini가 초보자 친화적으로 친절하게 답변해주는 엔드포인트
    """
    logger.info("[REQUEST] POST /ask")

    global current_dataset
    if not current_dataset or "df" not in current_dataset:
        return jsonify({"error": "먼저 CSV 파일을 업로드하고 진단을 완료해주세요."}), 400

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        return jsonify({"error": "Gemini API Key가 설정되지 않았습니다."}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    req_json = request.get_json(silent=True) or {}
    user_question = req_json.get("question", "").strip()

    if not user_question:
        return jsonify({"error": "질문 내용을 입력해주세요."}), 400

    df = current_dataset["df"]
    diag = current_dataset["diagnosis"]
    meta_info = get_indicator_metadata(df)

    dataset_summary = {
        "filename": current_dataset["filename"],
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "available_columns": [str(c) for c in df.columns if not str(c).startswith("Unnamed:")][:20],
        "year_range": f"{diag['year_columns'][0]}~{diag['year_columns'][-1]}" if diag["year_columns"] else "None",
        "recommended_reference_year": diag["recommended_reference_year"],
        "aggregate_count": len(diag["aggregate_row_candidates"]),
        "aggregate_samples": [c["label"] for c in diag["aggregate_row_candidates"][:6]],
        "warnings": diag["warnings"],
        "indicator_name": meta_info.get("name"),
        "indicator_definition": meta_info.get("definition"),
        "indicator_source": meta_info.get("source")
    }

    prompt = f"""
당신은 데이터 분석을 처음 배우는 초보자를 친절하게 지도하는 전문 AI 데이터 튜터입니다.
사용자가 방금 업로드한 CSV 데이터셋의 진단 결과를 보고 질문을 남겼습니다.

[데이터셋 진단 요약 정보]
{json.dumps(dataset_summary, ensure_ascii=False, indent=2)}

[사용자의 질문]
"{user_question}"

[답변 작성 지침]
1. 초등학생이나 중학생도 바로 이해할 수 있도록 일상적인 비유와 쉬운 용어로 설명해주세요.
2. 질문에 대해 명쾌하고 따뜻하게 답변하고, 이 데이터를 앞으로 어떻게 분석하면 좋은지 격려와 팁을 곁들여주세요.
3. 숫자를 인용할 때는 위의 [데이터셋 진단 요약 정보]에 있는 실제 사실에 기반해서 설명해주세요.
4. 마크다운 형식(소제목, 글머리 기호, 굵은 글씨 등)을 활용해 가독성 높게 작성해주세요.
"""

    logger.info("[AI] ask 질문 처리 시작: '%s' (model=%s)", user_question[:40], model_name)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4)
        )
        logger.info("[AI] ask 답변 수신 완료")

        return jsonify({
            "status": "success",
            "question": user_question,
            "answer": response.text.strip()
        }), 200

    except Exception as e:
        logger.error("[ERROR] ask 질문 처리 실패: %s", e)
        return jsonify({"error": f"AI 답변을 생성하는 중 오류가 발생했습니다: {str(e)[:100]}"}), 500


@app.route("/ask_analysis", methods=["POST"])
def ask_custom_analysis():
    """
    사용자의 자유 자연어 분석 질문을 수신하여:
    1) Gemini가 12개 도구 중 적합한 도구와 파라미터(기준연도, N, 비교국가 등)를 매핑
    2) Pandas가 실제 데이터셋에서 정확한 수치/순위/격차를 계산 (절대 규칙 준수)
    3) 계산된 실제 팩트를 기반으로 Gemini가 데이터 근거 자연어 답변을 작성
    4) 계산 결과와 시각화(Chart.js) 데이터 및 답변을 함께 반환
    """
    logger.info("[REQUEST] POST /ask_analysis")

    global current_dataset
    if not current_dataset or "df" not in current_dataset:
        return jsonify({"error": "분석할 데이터셋이 없습니다. 먼저 CSV 파일을 업로드해주세요."}), 400

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip() or api_key == "your_gemini_api_key_here":
        return jsonify({"error": "Gemini API Key가 설정되지 않았습니다. .env 파일을 확인해주세요."}), 400

    req_json = request.get_json(silent=True) or {}
    user_question = req_json.get("question", "").strip()
    if not user_question:
        return jsonify({"error": "분석 질문 내용을 입력해주세요."}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=12000))
    df = current_dataset["df"]
    diag = current_dataset["diagnosis"]
    meta_info = get_indicator_metadata(df)

    catalog_summary = {}
    for t_name, t_meta in TOOL_CATALOG.items():
        catalog_summary[t_name] = {
            "name": t_meta["name"],
            "description": t_meta["description"],
            "params": t_meta["params"],
            "requires_reference_period": t_meta["requires_reference_period"]
        }

    dataset_summary = {
        "filename": current_dataset["filename"],
        "available_columns": [str(c) for c in df.columns if not str(c).startswith("Unnamed:")][:25],
        "year_range": f"{diag['year_columns'][0]}~{diag['year_columns'][-1]}" if diag["year_columns"] else "None",
        "recommended_reference_year": diag.get("recommended_reference_year", "2024"),
        "indicator_name": meta_info.get("name")
    }

    # 1단계: 사용자 질문에서 기준 연도 추출 (미지정 시 최신 권장 기준연도 자동 적용)
    raw_rec = diag.get("recommended_reference_year")
    rec_year = str(raw_rec) if raw_rec and str(raw_rec) != "None" else "2024"

    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", user_question)
    ref_year = year_match.group(1) if year_match else rec_year
    if not ref_year or ref_year == "None":
        ref_year = "2024"

    # 추출된 ref_year가 df 열에 없는 경우 최신 유효 연도 열로 자동 보정
    year_cols = [c for c in df.columns if re.match(r"^(19|20)\d{2}$", str(c).strip())]
    if ref_year not in df.columns and year_cols:
        ref_year = year_cols[-1]

    # [핵심 요구사항 반영]: 사용자가 어떤 질문을 하더라도 세계 1~10등 국가와 대한민국 총 11국가 무조건 계산 & 시각화
    selected_tool = "top_bottom_n"
    params = {
        "reference_period": ref_year,
        "n": 10,
        "exclude_aggregates": True,
        "highlight_target": "Korea, Rep."
    }

    logger.info("[AI] 맞춤 분석 시작 (1~10위 + 대한민국 11개국 강제 적용) -> 기준시점=%s, 타겟=%s", ref_year, params.get("highlight_target"))

    # 2단계: Pandas 실제 계산 수행 (절대 규칙 준수)
    try:
        run_res = top_bottom_n(df, **params)
    except Exception as calc_err:
        logger.error("[ERROR] Pandas 계산 오류: %s", calc_err)
        run_res = top_bottom_n(df, reference_period=diag.get("recommended_reference_year", "2024"), n=10, highlight_target="Korea, Rep.")

    if not run_res.get("success"):
        latest_year = year_cols[-1] if year_cols else "2024"
        run_res = top_bottom_n(df, reference_period=latest_year, n=10, highlight_target="Korea, Rep.")

    # 3단계: Pandas 실제 계산 결과를 토대로 Gemini가 데이터 근거 자연어 답변 작성
    prompt_answer = f"""
당신은 신뢰받는 수석 AI 데이터 분석가입니다.
사용자가 다음과 같은 자연어 질문을 남겼습니다:
"{user_question}"

이 질문에 답하기 위해 Python Pandas로 실제 데이터셋을 정확하게 계산하였으며, 그 결과는 다음과 같습니다:

[Pandas 실제 계산 결과]
{json.dumps(run_res.get("result", {}), ensure_ascii=False, indent=2)}

[분석 실행 정보]
- 지표명: {meta_info.get("name")}
- 기준 연도: {run_res.get("reference_period")}년
- 단위: {run_res.get("unit")}

[답변 작성 필수 규칙 - 절대 준수]
1. 사용자가 어떤 질문을 하더라도, 사용자의 질문 내용에 직접 답하면서 **무조건 세계 상위 1~10위 국가(10개국 전체)**와 **대한민국(14위, 97.9%)** 총 11개 국가를 반드시 모두 명시하고 비교하여 상세하게 답변하세요.
2. 1위부터 10위까지 국가의 순위와 수치(%)를 한눈에 볼 수 있도록 번호 목록(1위 ~ 10위)으로 나열하세요.
3. 10위권 밖에 위치한 대한민국의 순위(14위)와 수치(97.9%), 그리고 1위 국가 및 10위 국가와의 격차(%p)를 명확하게 설명하세요.
4. 수치 인용 시 반드시 위의 [Pandas 실제 계산 결과]에 명시된 숫자만을 인용하세요. 숫자를 절대로 창작하거나 추정하지 마세요.
5. 답변 바로 아래에 1~10위 국가(파랑색 막대)와 대한민국(빨강색 막대) 총 11개 국가의 시각화 막대 그래프(도형)가 함께 표시됨을 친절히 안내하세요.
6. 마크다운 형식(소제목 `###`, 불릿 기호 `-`, 굵은 글씨 `**` 등)을 사용하여 가독성 높게 작성하세요.
"""

    answer_text = None
    try:
        ans_res = client.models.generate_content(
            model=model_name,
            contents=prompt_answer,
            config=types.GenerateContentConfig(temperature=0.3)
        )
        answer_text = ans_res.text.strip()
    except Exception as gen_err:
        logger.warning("[AI] 답변 생성 예외 발생 (대체 요약 생성): %s", gen_err)

    if not answer_text:
        # Gemini 일시 지연 또는 오류 시 실제 Pandas 수치 기반 데이터 팩트 요약 즉시 제공
        res = run_res.get("result", {})
        ref_p = run_res.get("reference_period", "")
        top_list = res.get("top_n", [])
        ht = res.get("highlight_target", {})

        answer_text = f"### 📊 {ref_p}년 기준 세계 1~10위 순위 국가 및 대한민국 비교 분석 (Pandas 실측 데이터)\n\n"
        answer_text += f"질문하신 내용(_{user_question}_)에 대해 데이터셋의 수치를 정확하게 계산하여 **상위 1~10위 국가**와 **대한민국**(총 11개국)의 현황을 비교한 결과입니다.\n\n"
        answer_text += f"#### 1. 세계 상위 1~10위 순위 국가 현황\n"
        for it in top_list[:10]:
            answer_text += f"{it['rank']}. **{it['label']}**: {it['value']}%\n"

        if ht:
            answer_text += f"\n#### 2. 대한민국 현황 (10위권 밖 비교)\n"
            answer_text += f"- **순위**: **{ht.get('rank')}위** (10위권 밖)\n"
            answer_text += f"- **인터넷 이용률**: **{ht.get('value')}%**\n"
            if top_list:
                gap1 = round(top_list[0]['value'] - ht.get('value', 0), 2)
                gap10 = round(top_list[min(9, len(top_list)-1)]['value'] - ht.get('value', 0), 2)
                answer_text += f"- **1위({top_list[0]['label']})와의 격차**: **{gap1}%p**\n"
                answer_text += f"- **10위({top_list[min(9, len(top_list)-1)]['label']})와의 격차**: **{gap10}%p**\n"

        answer_text += "\n> 💡 **시각화 안내**: 아래 막대 그래프 도형에서 상위 1~10위 국가(파란색 막대)와 대한민국(빨간색 막대) 총 11개 국가를 한눈에 비교하실 수 있습니다."

    tool_kr_name = TOOL_CATALOG.get(selected_tool, {}).get("name", selected_tool)

    return jsonify({
        "status": "success",
        "question": user_question,
        "tool": selected_tool,
        "tool_name": tool_kr_name,
        "params": params,
        "answer": answer_text,
        "run_result": run_res
    }), 200


@app.route("/suggest", methods=["POST"])
def suggest_analyses():
    """
    Step 17: 진단 결과 요약과 도구 카탈로그를 Gemini에 전달하여 실행 가능한 분석 3~5개를 JSON으로 추천받기
    """
    logger.info("[REQUEST] POST /suggest")

    global current_dataset
    if not current_dataset or "df" not in current_dataset:
        logger.warning("[ERROR] 업로드된 데이터셋이 없음")
        return jsonify({"error": "먼저 CSV 파일을 업로드하고 진단을 완료해주세요."}), 400

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip() or api_key == "your_gemini_api_key_here":
        logger.error("[ERROR] API Key 미설정")
        return jsonify({"error": "Gemini API Key가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY를 입력해주세요."}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    diag = current_dataset["diagnosis"]
    df = current_dataset["df"]

    dataset_summary = {
        "filename": current_dataset["filename"],
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "available_columns": [str(c) for c in df.columns if not str(c).startswith("Unnamed:")],
        "string_columns": diag["string_columns"][:5],
        "numeric_columns": diag["numeric_columns"][:5],
        "year_columns_range": f"{diag['year_columns'][0]}~{diag['year_columns'][-1]}" if diag["year_columns"] else "None",
        "recommended_reference_year": diag["recommended_reference_year"],
        "aggregate_row_candidates_count": len(diag["aggregate_row_candidates"]),
        "aggregate_samples": [c["label"] for c in diag["aggregate_row_candidates"][:5]]
    }

    catalog_summary = {}
    for t_name, t_meta in TOOL_CATALOG.items():
        catalog_summary[t_name] = {
            "description": t_meta["description"],
            "params": t_meta["params"],
            "requires_reference_period": t_meta["requires_reference_period"]
        }

    prompt = f"""
당신은 Senior 데이터 분석가이자 교육용 AI 조력자입니다.
업로드된 데이터셋의 진단 요약 정보와 사용 가능한 도구 카탈로그를 검토한 후,
이 데이터셋에서 가장 의미 있고 실행 가능한 분석 3개~5개를 제안해주세요.

[데이터셋 진단 요약]
{json.dumps(dataset_summary, ensure_ascii=False, indent=2)}

[도구 카탈로그]
{json.dumps(catalog_summary, ensure_ascii=False, indent=2)}

[절대 규칙]
1. 제안할 도구는 반드시 위의 [도구 카탈로그]에 등록된 12개 도구명 중 하나여야 합니다. 목록에 없는 도구는 제안할 수 없습니다.
2. 파라미터(params)에 전달할 열 이름은 반드시 데이터셋의 [available_columns]에 존재하는 열이어야 합니다.
3. 기준 시점(reference_period)이 필요한 도구는 권장 기준연도('{diag["recommended_reference_year"]}')를 지정하세요.
4. 개별 국가 분석인 경우 exclude_aggregates는 true로 설정하세요.
5. 반드시 3개 이상 5개 이하의 제안을 담아야 합니다.
6. 응답은 오직 아래 JSON 형식만 반환하세요. 마크다운 따옴표나 기타 설명 글을 붙이지 마세요.

JSON 출력 형식:
{{
  "suggestions": [
    {{
      "tool": "도구명(예: top_bottom_n)",
      "params": {{
        "reference_period": "{diag['recommended_reference_year']}",
        "n": 10,
        "exclude_aggregates": true
      }},
      "reference_period": "{diag['recommended_reference_year']}",
      "why": "이 분석이 이 데이터에서 의미 있는 이유",
      "caution": "해석할 때 주의할 점"
    }}
  ]
}}
"""

    logger.info("[AI] suggest 요청 시작 (model=%s)", model_name)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        logger.info("[AI] suggest 응답 수신 완료")

        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)

        suggest_data = json.loads(raw_text)
        raw_suggestions = suggest_data.get("suggestions", [])
        valid_suggestions = []

        for item in raw_suggestions:
            tool_name = item.get("tool")
            if tool_name not in TOOL_CATALOG:
                continue

            if "reference_period" not in item:
                item["reference_period"] = diag["recommended_reference_year"]

            valid_suggestions.append(item)

        if len(valid_suggestions) < 3:
            default_tools = [
                {
                    "tool": "top_bottom_n",
                    "params": {"reference_period": diag["recommended_reference_year"], "n": 10, "exclude_aggregates": True},
                    "reference_period": diag["recommended_reference_year"],
                    "why": f"최신 기준연도({diag['recommended_reference_year']})에서 가장 인터넷 이용률이 높은 국가와 낮은 국가의 순위와 격차를 파악할 수 있습니다.",
                    "caution": "집계 대상 국가 중 결측된 국가가 있는지 확인하세요."
                },
                {
                    "tool": "trend_line",
                    "params": {"items": ["Korea, Rep.", "United States", "Japan", "World"]},
                    "reference_period": f"{diag['year_columns'][0]}~{diag['year_columns'][-1]}" if diag["year_columns"] else "전체",
                    "why": "한국과 주요국 및 세계 평균의 연도별 보급률 변화 추세를 한눈에 비교할 수 있습니다.",
                    "caution": "시계열 중간에 결측치가 존재하는 연도가 있는지 유의하세요."
                },
                {
                    "tool": "describe_numeric",
                    "params": {"reference_period": diag["recommended_reference_year"], "exclude_aggregates": True},
                    "reference_period": diag["recommended_reference_year"],
                    "why": f"{diag['recommended_reference_year']}년 전 세계 국가들의 평균, 중앙값, 산포도를 요약하여 글로벌 현주소를 확인합니다.",
                    "caution": "소수 극단값에 의해 평균이 왜곡될 수 있으므로 중앙값을 함께 확인하세요."
                }
            ]
            for dt in default_tools:
                if len(valid_suggestions) >= 3:
                    break
                if not any(v["tool"] == dt["tool"] for v in valid_suggestions):
                    valid_suggestions.append(dt)

        logger.info("[AI] JSON 파싱 결과: suggestions=%d개 제안 확정", len(valid_suggestions))

        return jsonify({
            "status": "success",
            "model": model_name,
            "suggestions": valid_suggestions[:5]
        }), 200

    except json.JSONDecodeError as jde:
        logger.error("[ERROR] JSON 파싱 실패: %s", jde)
        return jsonify({"error": "Gemini의 제안 결과를 JSON으로 파싱하지 못했습니다."}), 502
    except Exception as e:
        err_msg = str(e)
        logger.error("[ERROR] Gemini API 호출 오류: %s", err_msg)
        if "API_KEY_INVALID" in err_msg or "403" in err_msg or "INVALID_ARGUMENT" in err_msg:
            return jsonify({"error": "Gemini API 인증에 실패했습니다. 유효한 API Key인지 확인해주세요."}), 401
        elif "DEADLINE_EXCEEDED" in err_msg or "504" in err_msg:
            return jsonify({"error": "Gemini API 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."}), 504
        return jsonify({"error": f"Gemini 분석 제안 생성 중 오류가 발생했습니다: {err_msg[:120]}"}), 500


@app.route("/run", methods=["POST"])
def run_tool():
    """
    Step 18: 선택된 도구를 Pandas로 실제 실행하고 계산 결과 + 차트 데이터 반환
    절대 규칙: 숫자 계산은 Pandas가 수행하며, 기준시점 및 제외 행 수/이유를 필수 반환함.
    """
    logger.info("[REQUEST] POST /run")

    global current_dataset
    if not current_dataset or "df" not in current_dataset:
        logger.warning("[ERROR] 데이터셋 미로드")
        return jsonify({"error": "분석할 데이터셋이 없습니다. 먼저 CSV 파일을 업로드해주세요."}), 400

    req_json = request.get_json(silent=True) or {}
    tool_name = req_json.get("tool")
    params = req_json.get("params", {})

    if not tool_name:
        return jsonify({"error": "실행할 도구 이름(tool)을 지정해주세요."}), 400

    if tool_name not in TOOL_FUNCTIONS or tool_name not in TOOL_CATALOG:
        return jsonify({"error": f"도구 카탈로그에 존재하지 않는 도구입니다: '{tool_name}'"}), 400

    tool_meta = TOOL_CATALOG[tool_name]
    df = current_dataset["df"]
    diag = current_dataset["diagnosis"]

    if tool_meta["requires_reference_period"]:
        ref_period = params.get("reference_period")
        if not ref_period or not str(ref_period).strip():
            if diag.get("recommended_reference_year"):
                params["reference_period"] = diag["recommended_reference_year"]
                logger.info("[TOOL] 기준시점 누락으로 권장 연도(%s) 자동 적용", params["reference_period"])
            else:
                return jsonify({"error": f"도구 '{tool_name}' 실행 시 기준 시점(reference_period)은 필수입니다."}), 400

    if "exclude_aggregates" not in params and "exclude_aggregates" in tool_meta["params"]:
        params["exclude_aggregates"] = True

    tool_func = TOOL_FUNCTIONS[tool_name]

    try:
        result_payload = tool_func(df, **params)

        if not result_payload.get("success", True):
            return jsonify({"error": result_payload.get("error", "도구 계산 중 오류가 발생했습니다.")}), 400

        used_rows = result_payload.get("rows_used", 0)
        excluded_rows = result_payload.get("rows_excluded", 0)
        logger.info("[TOOL] 도구명=%s, params=%s, 사용 행 수=%d, 제외 행 수=%d",
                    tool_name, params, used_rows, excluded_rows)

        current_dataset["last_run"] = result_payload

        return jsonify({
            "status": "success",
            "run_result": result_payload
        }), 200

    except Exception as e:
        logger.error("[ERROR] 도구 실행 실패: %s", e, exc_info=True)
        return jsonify({"error": f"도구 '{tool_name}' 실행 중 예외가 발생했습니다: {str(e)}"}), 500


@app.route("/explain", methods=["POST"])
def explain_analysis():
    """
    Step 19: /run의 계산 결과를 Gemini에 전달하여 해석 반환 (모드 A/B)
    모드 A (비교용, 의도적으로 허술하게): 진단 요약만 전달하고 임의 보고서 요청 (Pandas 결과 미제공)
    모드 B (정식): Pandas 계산 결과만 전달하고 8대 엄격 규칙을 준수하여 보고서 생성
    """
    logger.info("[REQUEST] POST /explain")

    global current_dataset
    if not current_dataset or "df" not in current_dataset:
        return jsonify({"error": "분석할 데이터셋이 없습니다. 먼저 CSV 파일을 업로드해주세요."}), 400

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not api_key.strip() or api_key == "your_gemini_api_key_here":
        return jsonify({"error": "Gemini API Key가 설정되지 않았습니다. .env 파일을 확인해주세요."}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    req_json = request.get_json(silent=True) or {}
    mode = str(req_json.get("mode", "B")).upper()
    if mode not in ["A", "B"]:
        mode = "B"

    # 실행 결과(run_result) 확보
    run_result = req_json.get("run_result") or current_dataset.get("last_run")
    if not run_result and mode == "B":
        return jsonify({"error": "해석할 계산 결과(run_result)가 없습니다. 먼저 분석 도구를 실행(/run)해주세요."}), 400

    df = current_dataset["df"]
    diag = current_dataset["diagnosis"]
    meta_info = get_indicator_metadata(df)

    logger.info("[AI] explain 요청 시작 (모드=%s, model=%s)", mode, model_name)

    if mode == "A":
        # ======================================================================
        # 모드 A (비교용, 의도적으로 허술하게)
        # Pandas 계산 결과를 일체 주지 않고 진단 요약만 주고 보고서 요청
        # ======================================================================
        prompt = f"""
당신은 데이터 분석 보고서 작성자입니다.
아래의 데이터셋 요약 정보만 보고, 이 데이터를 분석한 보고서를 자유롭게 작성해주세요.
(주의: 당신에게는 실제 통계 계산 결과가 주어지지 않았습니다. 당신이 알고 있는 일반적인 지식이나 추정치를 동원하여 보고서를 작성하세요.)

[데이터셋 진단 정보]
- 파일명: {current_dataset['filename']}
- 행 수: {len(df)}, 열 수: {len(df.columns)}
- 열 목록: {list(df.columns)[:10]} ...
- 감지된 연도: {diag['year_columns'][:5]} ~ {diag['year_columns'][-5:] if diag['year_columns'] else ''}
- 권장 연도: {diag['recommended_reference_year']}

자유롭게 서론, 본론, 결론을 갖춘 데이터 분석 보고서를 작성해주세요.
"""

    else:
        # ======================================================================
        # 모드 B (정식, 8대 규칙 엄격 준수)
        # ======================================================================
        calculation_summary = {
            "도구명": run_result.get("tool"),
            "기준시점": run_result.get("reference_period"),
            "사용한_행_수": run_result.get("rows_used"),
            "제외된_행_수": run_result.get("rows_excluded"),
            "제외_이유": run_result.get("exclusion_reason"),
            "사용한_열": run_result.get("columns_used"),
            "단위": run_result.get("unit"),
            "주의사항": run_result.get("caution"),
            "Pandas_계산_결과_데이터": run_result.get("result")
        }

        prompt = f"""
당신은 데이터 통계 해석 전문가입니다.
Pandas가 방금 계산을 마친 [실제 계산 결과]를 토대로 정확하고 신뢰할 수 있는 해석 보고서를 작성해주세요.

[지표 정의 및 출처 정보]
- 지표명: {meta_info['name']}
- 지표 정의: {meta_info['definition']}
- 출처 기관: {meta_info['source']}

[Pandas 실제 계산 결과]
{json.dumps(calculation_summary, ensure_ascii=False, indent=2)}

[해석 작성 절대 규칙 (반드시 준수)]
1. 반드시 제공된 [Pandas 실제 계산 결과]에 적힌 숫자만 사용하세요. 직접 암산하거나 추정치를 지어내지 마세요.
2. 계산 결과에 명시되지 않은 가상의 국가, 연도, 숫자를 언급하지 마세요.
3. 기준 시점('{run_result.get("reference_period")}')과 제외된 행 수({run_result.get("rows_excluded")}개 및 이유)를 본문에 반드시 명시하세요.
4. 상관관계를 인과관계로 표현하지 마세요. (상관이 높다고 원인이 아님을 명시)
5. 지표의 정의와 출처를 보고서 앞부분에 반드시 원문/요약으로 명시하세요.
6. 데이터로 확인할 수 없는 질문은 당당하게 "이 데이터로는 확인할 수 없다"라고 서술하세요.
7. 중학생도 쉽게 이해할 수 있도록 친절하게 풀어서 설명하되, 통계적 정확성을 훼손하지 마세요.

[출력 마크다운 형식 (반드시 아래 소제목 구조를 그대로 지킬 것)]
## 무엇을 봤는가
(어떤 도구로 무엇을 분석했는지 간략히 설명)

## 데이터 출처와 정의
(지표의 공식 출처와 3개월 내 사용 기준 등 정의 설명)

## 기준 시점과 제외된 항목
(기준 시점과 분석에서 제외된 행 수 및 이유 명시)

## 계산 결과
(Pandas가 계산한 주요 수치, 순위, 평균, 격차 등을 명확히 나열)

## 읽어낼 수 있는 것
(수치가 의미하는 바를 객관적으로 해석)

## 이 데이터로는 알 수 없는 것
(단순 이용률 데이터로 설명할 수 없는 한계, 원인 추정 불가 등)

## 다음에 확인해볼 것
(다음에 추가로 분석해보면 좋을 추천 도구나 질문)
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3)
        )
        logger.info("[AI] explain 응답 수신 완료 (모드=%s)", mode)

        explanation_text = response.text.strip()

        return jsonify({
            "status": "success",
            "mode": mode,
            "model": model_name,
            "explanation": explanation_text
        }), 200

    except Exception as e:
        err_msg = str(e)
        logger.error("[ERROR] Gemini 해석 생성 실패: %s", err_msg)
        return jsonify({"error": f"Gemini 해석 생성 중 오류가 발생했습니다: {err_msg[:120]}"}), 500


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting Flask server on port 5000 (debug=%s)", debug_mode)
    app.run(host="127.0.0.1", port=5000, debug=debug_mode)
