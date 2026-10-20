/**
 * AI Data Insight Builder - Frontend Logic (Vanilla JS + Chart.js)
 */

document.addEventListener("DOMContentLoaded", () => {
  // 전역 상태 변수
  let selectedFile = null;
  let inspectionData = null;
  let lastRunResult = null;
  let activeMode = "B";
  let analysisChartInstance = null;

  // DOM 요소 참조
  const serverBadge = document.getElementById("serverBadge");
  const apiKeyBadge = document.getElementById("apiKeyBadge");
  const errorBanner = document.getElementById("errorBanner");
  const errorMessage = document.getElementById("errorMessage");
  const closeErrorBtn = document.getElementById("closeErrorBtn");

  const dropZone = document.getElementById("dropZone");
  const csvFileInput = document.getElementById("csvFileInput");
  const selectedFileInfo = document.getElementById("selectedFileInfo");
  const btnInspect = document.getElementById("btnInspect");

  const sectionDiagnosis = document.getElementById("sectionDiagnosis");
  const diagEncoding = document.getElementById("diagEncoding");
  const diagSkippedRows = document.getElementById("diagSkippedRows");
  const diagShape = document.getElementById("diagShape");
  const diagRecYear = document.getElementById("diagRecYear");
  const diagAggCount = document.getElementById("diagAggCount");
  const diagDuplicates = document.getElementById("diagDuplicates");
  const diagWarningsBox = document.getElementById("diagWarningsBox");
  const diagWarningsList = document.getElementById("diagWarningsList");
  const previewTableHead = document.getElementById("previewTableHead");
  const previewTableBody = document.getElementById("previewTableBody");
  const btnRequestSuggest = document.getElementById("btnRequestSuggest");

  const sectionSuggestions = document.getElementById("sectionSuggestions");
  const suggestionsList = document.getElementById("suggestionsList");
  const selectManualTool = document.getElementById("selectManualTool");
  const inputManualRefPeriod = document.getElementById("inputManualRefPeriod");
  const btnRunManual = document.getElementById("btnRunManual");

  const sectionRunResult = document.getElementById("sectionRunResult");
  const resToolName = document.getElementById("resToolName");
  const resRefPeriod = document.getElementById("resRefPeriod");
  const resRowsUsed = document.getElementById("resRowsUsed");
  const resRowsExcluded = document.getElementById("resRowsExcluded");
  const resUnit = document.getElementById("resUnit");
  const resExclusionReasonBox = document.getElementById("resExclusionReasonBox");
  const resExclusionReason = document.getElementById("resExclusionReason");
  const chartContainer = document.getElementById("chartContainer");
  const analysisChartCanvas = document.getElementById("analysisChart");
  const resultContent = document.getElementById("resultContent");
  const resCautionText = document.getElementById("resCautionText");
  const btnScrollToExplain = document.getElementById("btnScrollToExplain");

  const sectionExplain = document.getElementById("sectionExplain");
  const btnModeB = document.getElementById("btnModeB");
  const btnModeA = document.getElementById("btnModeA");
  const btnGenerateExplain = document.getElementById("btnGenerateExplain");
  const explainLoading = document.getElementById("explainLoading");
  const reportContainer = document.getElementById("reportContainer");
  const reportModeBadge = document.getElementById("reportModeBadge");
  const reportModelBadge = document.getElementById("reportModelBadge");
  const reportContent = document.getElementById("reportContent");
  const btnCopyReport = document.getElementById("btnCopyReport");

  // ============================================================================
  // Security Password Gate (무조건 접속 시 비밀번호 입력 필수: 0909)
  // ============================================================================
  const authGateOverlay = document.getElementById("authGateOverlay");
  const authCard = document.getElementById("authCard");
  const authPasswordInput = document.getElementById("authPasswordInput");
  const btnTogglePassword = document.getElementById("btnTogglePassword");
  const authErrorMessage = document.getElementById("authErrorMessage");
  const authForm = document.getElementById("authForm");

  const APP_PASSWORD = "0909";

  // 접속 시도 시 항상 비밀번호 입력창에 포커스 (기존 입력 초기화)
  if (authPasswordInput) {
    authPasswordInput.value = "";
    setTimeout(() => {
      authPasswordInput.focus();
    }, 150);
  }

  // 비밀번호 보이기 / 숨기기 토글
  if (btnTogglePassword && authPasswordInput) {
    btnTogglePassword.addEventListener("click", () => {
      const isPass = authPasswordInput.type === "password";
      authPasswordInput.type = isPass ? "text" : "password";
      btnTogglePassword.textContent = isPass ? "🙈" : "👁️";
    });
  }

  // 비밀번호 제출 및 검증 처리
  async function handleAuthSubmit() {
    const entered = (authPasswordInput.value || "").trim();

    if (!entered) {
      showAuthError("비밀번호를 입력해주세요.");
      return;
    }

    if (entered === APP_PASSWORD) {
      // 인증 성공: 자물쇠 해제 및 메인 화면 표시
      unlockApp();

      // 서버 세션도 안전하게 인증 동기화
      try {
        await fetch("/api/verify_password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: entered })
        });
      } catch (e) {
        console.warn("[Auth] 서버 세션 동기화 예외:", e);
      }
    } else {
      showAuthError("비밀번호가 올바르지 않습니다. 다시 확인해주세요.");
    }
  }

  function showAuthError(msg) {
    if (authErrorMessage) {
      authErrorMessage.textContent = msg;
      authErrorMessage.classList.remove("hidden");
      authErrorMessage.style.display = "block";
    }
    if (authCard) {
      authCard.classList.remove("shake");
      void authCard.offsetWidth; // DOM 리플로우를 통한 애니메이션 재트리거
      authCard.classList.add("shake");
    }
    if (authPasswordInput) {
      authPasswordInput.value = "";
      authPasswordInput.focus();
    }
  }

  function unlockApp() {
    if (authErrorMessage) {
      authErrorMessage.classList.add("hidden");
      authErrorMessage.style.display = "none";
    }
    if (authGateOverlay) {
      authGateOverlay.classList.add("unlocked");
      setTimeout(() => {
        authGateOverlay.style.display = "none";
      }, 350);
    }
  }

  if (authForm) {
    authForm.addEventListener("submit", (e) => {
      e.preventDefault();
      handleAuthSubmit();
    });
  }

  // ============================================================================
  // 유틸리티 함수: 에러 표시 및 콘솔 로그
  // ============================================================================
  function showError(msg) {
    console.error(`[ERROR] ${msg}`);
    errorMessage.textContent = msg;
    errorBanner.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function hideError() {
    errorBanner.classList.add("hidden");
    errorMessage.textContent = "";
  }

  closeErrorBtn.addEventListener("click", hideError);

  // 12개 전체 도구 목록 (수동 선택용)
  const ALL_TOOLS = [
    { id: "top_bottom_n", name: "top_bottom_n (상·하위 N 순위)", reqPeriod: true },
    { id: "trend_line", name: "trend_line (연도별 추이 선 차트)", reqPeriod: false },
    { id: "change_rate", name: "change_rate (두 시점 간 변화량·변화율)", reqPeriod: true },
    { id: "distribution", name: "distribution (구간별 분포 히스토그램)", reqPeriod: true },
    { id: "compare_one_vs_all", name: "compare_one_vs_all (특정 항목 vs 전체 평균)", reqPeriod: true },
    { id: "group_summary", name: "group_summary (그룹·소득군별 요약)", reqPeriod: true },
    { id: "describe_numeric", name: "describe_numeric (기술통계량 요약)", reqPeriod: false },
    { id: "correlation_scatter", name: "correlation_scatter (상관관계 산점도)", reqPeriod: true },
    { id: "year_coverage", name: "year_coverage (연도별 충실도 분석)", reqPeriod: false },
    { id: "detect_aggregates", name: "detect_aggregates (집계 행 후보 탐지)", reqPeriod: false },
    { id: "quality_report", name: "quality_report (데이터 품질 상세 진단)", reqPeriod: false },
    { id: "reshape_wide_to_long", name: "reshape_wide_to_long (와이드→롱 변환)", reqPeriod: false }
  ];

  // ============================================================================
  // 초기화: 서버 상태 체크 및 페이지 로드
  // ============================================================================
  async function init() {
    hideError();
    try {
      const res = await fetch("/health");
      if (res.ok) {
        hideError();
        const data = await res.json();
        serverBadge.textContent = "서버 정상 온라인";
        serverBadge.className = "status-badge online";

        if (data.api_key_configured) {
          apiKeyBadge.textContent = `API 키 설정됨 (${data.gemini_model || "Gemini"})`;
          apiKeyBadge.className = "status-badge online";
        } else {
          apiKeyBadge.textContent = "API 키 미설정 (.env 확인 필요)";
          apiKeyBadge.className = "status-badge offline";
        }
      } else {
        serverBadge.textContent = "서버 응답 오류";
        serverBadge.className = "status-badge offline";
      }
    } catch (e) {
      serverBadge.textContent = "서버 연결 불가";
      serverBadge.className = "status-badge offline";
      showError("백엔드 서버에 연결할 수 없습니다. Flask 서버가 실행 중인지 확인하세요.");
    }

    // 수동 선택 드롭다운 채우기
    ALL_TOOLS.forEach(t => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.name;
      selectManualTool.appendChild(opt);
    });

    console.log("[PAGE] 페이지 로드 완료");
  }

  // ============================================================================
  // Step 1: 파일 선택 및 드래그 앤 드롭
  // ============================================================================
  function handleFileSelected(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      showError("CSV 형식의 파일(.csv)만 업로드할 수 있습니다.");
      return;
    }
    selectedFile = file;
    hideError();

    const sizeKb = (file.size / 1024).toFixed(1);
    selectedFileInfo.textContent = `선택된 파일: ${file.name} (${sizeKb} KB)`;
    selectedFileInfo.classList.remove("hidden");
    btnInspect.disabled = false;

    console.log(`[UPLOAD] 파일 선택 (파일명: ${file.name}, 크기: ${file.size} bytes)`);
  }

  csvFileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleFileSelected(e.target.files[0]);
    }
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  // ============================================================================
  // Step 1 -> Step 2: 진단 요청 (/inspect)
  // ============================================================================
  btnInspect.addEventListener("click", async () => {
    if (!selectedFile) return;
    hideError();
    btnInspect.disabled = true;
    btnInspect.textContent = "진단 분석 중...";

    console.log("[INSPECT] 진단 요청 시작");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const res = await fetch("/inspect", {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "파일 진단 중 오류가 발생했습니다.");
      }

      inspectionData = data;
      console.log(`[INSPECT] 응답 수신 (행 수: ${data.row_count}, 열 수: ${data.column_count}, 경고 수: ${data.warnings.length})`);

      // 진단 메트릭 업데이트
      diagEncoding.textContent = data.encoding;
      diagSkippedRows.textContent = `${data.skipped_rows}줄 스킵`;
      diagShape.textContent = `${data.row_count.toLocaleString()}행 × ${data.column_count}열`;
      diagRecYear.textContent = data.recommended_reference_year ? `${data.recommended_reference_year}년` : "감지 안 됨";
      diagAggCount.textContent = `${data.aggregate_row_candidates.length}개 행`;
      diagDuplicates.textContent = `${data.duplicate_rows_count}개`;

      // 경고 목록 렌더링
      if (data.warnings && data.warnings.length > 0) {
        diagWarningsList.innerHTML = "";
        data.warnings.forEach(w => {
          const li = document.createElement("li");
          li.textContent = w;
          diagWarningsList.appendChild(li);
        });
        diagWarningsBox.classList.remove("hidden");
      } else {
        diagWarningsBox.classList.add("hidden");
      }

      // 미리보기 테이블 렌더링
      renderPreviewTable(data.columns, data.preview_rows);

      // QA 영역 초기 상태로 초기화 (질문 전에는 숨김)
      if (qaLoading) {
        qaLoading.classList.add("hidden");
        qaLoading.style.display = "none";
      }
      if (qaAnswerBox) {
        qaAnswerBox.classList.add("hidden");
        qaAnswerBox.style.display = "none";
      }
      if (inputQaQuestion) {
        inputQaQuestion.value = "";
      }
      if (qaAnswerContent) {
        qaAnswerContent.innerHTML = "";
      }

      // 맞춤 자연어 분석 영역 초기화
      if (customChartInstance) {
        customChartInstance.destroy();
        customChartInstance = null;
      }
      if (customLoading) {
        customLoading.classList.add("hidden");
        customLoading.style.display = "none";
      }
      if (customResultBox) {
        customResultBox.classList.add("hidden");
        customResultBox.style.display = "none";
      }
      if (inputCustomQuestion) {
        inputCustomQuestion.value = "";
      }
      if (customAnswerContent) {
        customAnswerContent.innerHTML = "";
      }
      lastCustomAnalysisData = null;

      // 섹션 표시
      sectionDiagnosis.classList.remove("hidden");
      sectionDiagnosis.scrollIntoView({ behavior: "smooth" });

      // 수동 선택 기준연도 인풋 기본값 채우기
      if (data.recommended_reference_year) {
        inputManualRefPeriod.value = data.recommended_reference_year;
      }

    } catch (err) {
      showError(err.message);
    } finally {
      btnInspect.disabled = false;
      btnInspect.textContent = "🔍 데이터 상태 진단 시작";
    }
  });

  function renderPreviewTable(columns, rows) {
    previewTableHead.innerHTML = "";
    previewTableBody.innerHTML = "";

    // 헤더 행
    const thIdx = document.createElement("th");
    thIdx.textContent = "#";
    previewTableHead.appendChild(thIdx);

    columns.forEach(col => {
      const th = document.createElement("th");
      th.textContent = col;
      previewTableHead.appendChild(th);
    });

    // 데이터 행 (최대 10개)
    rows.forEach((row, i) => {
      const tr = document.createElement("tr");
      const tdIdx = document.createElement("td");
      tdIdx.textContent = i + 1;
      tdIdx.style.color = "#94a3b8";
      tr.appendChild(tdIdx);

      columns.forEach(col => {
        const td = document.createElement("td");
        const val = row[col];
        td.textContent = (val === null || val === undefined) ? "-" : val;
        tr.appendChild(td);
      });
      previewTableBody.appendChild(tr);
    });
  }

  // ============================================================================
  // Step 2: 데이터 진단 후속 질문 질의응답 (Q&A /ask)
  // ============================================================================
  const inputQaQuestion = document.getElementById("inputQaQuestion");
  const btnSubmitQa = document.getElementById("btnSubmitQa");
  const qaLoading = document.getElementById("qaLoading");
  const qaAnswerBox = document.getElementById("qaAnswerBox");
  const qaAnswerContent = document.getElementById("qaAnswerContent");
  const btnCloseQaAnswer = document.getElementById("btnCloseQaAnswer");
  const qaChips = document.querySelectorAll(".qa-chip");

  async function submitDiagnosisQuestion(question) {
    if (!question || !question.trim()) {
      showError("질문 내용을 입력해주세요.");
      return;
    }

    hideError();
    // 질문이 들어왔을 때 로딩 표시, 기존 답변은 숨김
    qaLoading.classList.remove("hidden");
    qaLoading.style.display = "flex";
    qaAnswerBox.classList.add("hidden");
    qaAnswerBox.style.display = "none";
    btnSubmitQa.disabled = true;

    console.log(`[QA] 질문 요청: "${question}"`);

    try {
      const res = await fetch("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "답변을 불러오지 못했습니다.");
      }

      console.log("[QA] 응답 수신 완료");
      // 쉬운 설명이 나오면 로딩을 다시 숨기고 답변 박스 표시
      qaLoading.classList.add("hidden");
      qaLoading.style.display = "none";
      qaAnswerContent.innerHTML = marked.parse(data.answer || "");
      qaAnswerBox.classList.remove("hidden");
      qaAnswerBox.style.display = "block";
      qaAnswerBox.scrollIntoView({ behavior: "smooth" });

    } catch (err) {
      showError(err.message);
    } finally {
      qaLoading.classList.add("hidden");
      qaLoading.style.display = "none";
      btnSubmitQa.disabled = false;
    }
  }

  btnSubmitQa.addEventListener("click", () => {
    submitDiagnosisQuestion(inputQaQuestion.value);
  });

  inputQaQuestion.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      submitDiagnosisQuestion(inputQaQuestion.value);
    }
  });

  qaChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const qText = chip.textContent.replace(/^💡\s*/, "");
      inputQaQuestion.value = qText;
      submitDiagnosisQuestion(qText);
    });
  });

  btnCloseQaAnswer.addEventListener("click", () => {
    qaAnswerBox.classList.add("hidden");
    qaAnswerBox.style.display = "none";
  });

  // ============================================================================
  // Step 2.5: 자연어 맞춤 분석 질문 창 (Natural Language Custom Analysis)
  // ============================================================================
  const inputCustomQuestion = document.getElementById("inputCustomQuestion");
  const btnSubmitCustom = document.getElementById("btnSubmitCustom");
  const customLoading = document.getElementById("customLoading");
  const customResultBox = document.getElementById("customResultBox");
  const customAnswerContent = document.getElementById("customAnswerContent");
  const customToolBadge = document.getElementById("customToolBadge");
  const btnCloseCustomResult = document.getElementById("btnCloseCustomResult");
  const btnGoToCustomViz = document.getElementById("btnGoToCustomViz");
  const customChips = document.querySelectorAll(".custom-chip");

  let lastCustomAnalysisData = null;
  let customChartInstance = null;

  function renderCustomChart(chartData, resultData) {
    const container = document.getElementById("customChartContainer");
    if (!chartData || !chartData.labels || chartData.labels.length === 0) {
      if (container) container.style.display = "none";
      return;
    }

    if (container) container.style.display = "block";

    // 1. 핵심 통계 지표 카드 렌더링
    const statCardsBox = document.getElementById("customStatCards");
    if (statCardsBox && resultData) {
      let cardsHtml = "";
      if (resultData.top_1) {
        cardsHtml += `
          <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 12px;">
            <div style="font-size: 11px; color: #1e40af; font-weight: 600;">👑 1위 국가</div>
            <div style="font-size: 14px; font-weight: 700; color: #1e3a8a; margin-top: 4px;">${resultData.top_1.label}</div>
            <div style="font-size: 13px; color: #3b82f6; font-weight: 700;">${resultData.top_1.value}%</div>
          </div>
        `;
      }
      if (resultData.highlight_target) {
        cardsHtml += `
          <div style="background: #fef2f2; border: 1.5px solid #fca5a5; border-radius: 8px; padding: 12px;">
            <div style="font-size: 11px; color: #991b1b; font-weight: 700;">🎯 대한민국 비교</div>
            <div style="font-size: 14px; font-weight: 700; color: #b91c1c; margin-top: 4px;">${resultData.highlight_target.label}</div>
            <div style="font-size: 13px; color: #ef4444; font-weight: 700;">${resultData.highlight_target.rank}위 (${resultData.highlight_target.value}%)</div>
          </div>
        `;
      }
      const displayGap = (resultData.korea_gap !== undefined && resultData.korea_gap !== null) ? resultData.korea_gap : resultData.gap;
      const gapLabel = (resultData.korea_gap !== undefined && resultData.korea_gap !== null) ? "1위 대비 대한민국 격차" : "1위와의 격차";
      if (displayGap !== undefined && displayGap !== null) {
        cardsHtml += `
          <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;">
            <div style="font-size: 11px; color: #64748b; font-weight: 600;">⚡ ${gapLabel}</div>
            <div style="font-size: 14px; font-weight: 700; color: #334155; margin-top: 4px;">${displayGap}%p</div>
            <div style="font-size: 12px; color: #64748b;">이용률 격차</div>
          </div>
        `;
      }
      statCardsBox.innerHTML = cardsHtml;
    }

    // 2. 직관적인 HTML 막대 바 렌더링 (어떤 브라우저 환경에서도 100% 선명하게 보이는 컬러 바 도형)
    const visualizerBox = document.getElementById("customBarVisualizer");
    if (visualizerBox && chartData.datasets && chartData.datasets[0]) {
      const labels = chartData.labels;
      const values = chartData.datasets[0].data;
      const colors = chartData.datasets[0].backgroundColor || [];
      const maxVal = Math.max(...values, 100);

      let barsHtml = `<div style="display: flex; flex-direction: column; gap: 8px;">`;
      labels.forEach((lbl, idx) => {
        const val = values[idx];
        const isRed = (Array.isArray(colors) && colors[idx] === "#ef4444") || lbl.includes("대한민국") || lbl.includes("Korea");
        const barColor = isRed ? "#ef4444" : "#3b82f6";
        const widthPct = Math.min(100, Math.max(6, (val / maxVal) * 100));

        barsHtml += `
          <div style="display: flex; align-items: center; gap: 10px; ${isRed ? 'background: #fff1f2; padding: 6px 10px; border-radius: 6px; border: 1.5px solid #fda4af;' : ''}">
            <div style="width: 175px; min-width: 175px; font-size: 13px; font-weight: ${isRed ? '700' : '500'}; color: ${isRed ? '#b91c1c' : '#334155'}; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
              ${isRed ? '🔴 ' : `${idx + 1}. `}${lbl}
            </div>
            <div style="flex: 1; background: #f1f5f9; border-radius: 4px; height: ${isRed ? '24px' : '20px'}; overflow: hidden; position: relative;">
              <div style="width: ${widthPct}%; height: 100%; background: ${barColor}; border-radius: 4px; transition: width 0.4s ease;"></div>
            </div>
            <div style="width: 70px; text-align: right; font-size: 13px; font-weight: 700; color: ${isRed ? '#b91c1c' : '#1e40af'};">
              ${val}%
            </div>
          </div>
        `;
      });
      barsHtml += `</div>`;
      visualizerBox.innerHTML = barsHtml;
    }

    // 3. Chart.js 캔버스 렌더링
    const canvas = document.getElementById("customChartCanvas");
    if (canvas) {
      const ctx = canvas.getContext("2d");

      if (customChartInstance) {
        customChartInstance.destroy();
        customChartInstance = null;
      }

      customChartInstance = new Chart(ctx, {
        type: chartData.type || "bar",
        data: {
          labels: chartData.labels,
          datasets: chartData.datasets
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: chartData.datasets && chartData.datasets.length > 1,
              position: "top"
            },
            tooltip: {
              callbacks: {
                label: function(context) {
                  return ` ${context.label}: ${context.raw}%`;
                }
              }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: {
                callback: function(value) { return value + "%"; }
              }
            }
          }
        }
      });
    }
  }

  async function submitCustomAnalysis(question) {
    if (!question || !question.trim()) {
      showError("분석하고 싶은 질문 내용을 입력해주세요.");
      return;
    }

    hideError();
    customLoading.classList.remove("hidden");
    customLoading.style.display = "flex";
    customResultBox.classList.add("hidden");
    customResultBox.style.display = "none";
    btnSubmitCustom.disabled = true;

    console.log(`[CUSTOM_ANALYSIS] 맞춤 분석 요청: "${question}"`);

    try {
      const res = await fetch("/ask_analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "맞춤 분석 수행 중 오류가 발생했습니다.");
      }

      console.log(`[CUSTOM_ANALYSIS] 응답 수신 완료 (도구: ${data.tool})`);
      lastCustomAnalysisData = data;

      customToolBadge.textContent = `${data.tool} (${data.tool_name || ""})`;
      customAnswerContent.innerHTML = marked.parse(data.answer || "");

      // 먼저 결과 박스를 DOM에 display: block으로 노출
      customLoading.classList.add("hidden");
      customLoading.style.display = "none";

      customResultBox.classList.remove("hidden");
      customResultBox.style.display = "block";

      // 부모 컨테이너가 노출된 상태에서 차트 및 막대 비주얼라이저 도형 렌더링
      if (data.run_result && data.run_result.chart_data) {
        setTimeout(() => {
          renderCustomChart(data.run_result.chart_data, data.run_result.result);
        }, 60);
      } else {
        renderCustomChart(null, null);
      }

      customResultBox.scrollIntoView({ behavior: "smooth" });

    } catch (err) {
      showError(err.message);
    } finally {
      customLoading.classList.add("hidden");
      customLoading.style.display = "none";
      btnSubmitCustom.disabled = false;
    }
  }

  btnSubmitCustom.addEventListener("click", () => {
    submitCustomAnalysis(inputCustomQuestion.value);
  });

  inputCustomQuestion.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      submitCustomAnalysis(inputCustomQuestion.value);
    }
  });

  customChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const qText = chip.textContent.replace(/^[📊📈🌍🚀💡]\s*/, "");
      inputCustomQuestion.value = qText;
      submitCustomAnalysis(qText);
    });
  });

  if (btnCloseCustomResult) {
    btnCloseCustomResult.addEventListener("click", () => {
      customResultBox.classList.add("hidden");
      customResultBox.style.display = "none";
    });
  }

  if (btnGoToCustomViz) {
    btnGoToCustomViz.addEventListener("click", () => {
      if (!lastCustomAnalysisData || !lastCustomAnalysisData.run_result) {
        showError("표시할 분석 결과 데이터가 없습니다.");
        return;
      }
      applyRunResult(lastCustomAnalysisData.run_result, lastCustomAnalysisData.tool, lastCustomAnalysisData.params);
    });
  }

  btnRequestSuggest.addEventListener("click", async () => {
    hideError();
    btnRequestSuggest.disabled = true;
    btnRequestSuggest.textContent = "💡 Gemini 분석 제안 생성 중...";

    console.log("[SUGGEST] 제안 요청 시작");

    try {
      const res = await fetch("/suggest", { method: "POST" });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "분석 제안 생성 중 오류가 발생했습니다.");
      }

      const suggestions = data.suggestions || [];
      console.log(`[SUGGEST] 응답 수신 (제안 개수: ${suggestions.length}개)`);

      renderSuggestions(suggestions);
      sectionSuggestions.classList.remove("hidden");
      sectionSuggestions.scrollIntoView({ behavior: "smooth" });

    } catch (err) {
      showError(err.message);
    } finally {
      btnRequestSuggest.disabled = false;
      btnRequestSuggest.textContent = "💡 Gemini에게 실행 가능한 분석 제안받기";
    }
  });

  function renderSuggestions(suggestions) {
    suggestionsList.innerHTML = "";
    suggestions.forEach(item => {
      const card = document.createElement("div");
      card.className = "suggestion-card";

      card.innerHTML = `
        <div class="card-content">
          <div class="card-top">
            <span class="tool-name-badge">${item.tool}</span>
            <span class="ref-period-tag">${item.reference_period ? `기준: ${item.reference_period}년` : "전체 시점"}</span>
          </div>
          <p class="sugg-why"><strong>🎯 제안 이유:</strong> ${item.why}</p>
          <div class="sugg-caution"><strong>⚠️ 주의점:</strong> ${item.caution}</div>
        </div>
        <button class="btn btn-primary btn-run-suggest" style="width: 100%;">
          ⚡ 이 분석 실행하기
        </button>
      `;

      card.querySelector(".btn-run-suggest").addEventListener("click", () => {
        runAnalysisTool(item.tool, item.params || { reference_period: item.reference_period });
      });

      suggestionsList.appendChild(card);
    });
  }

  // 수동 실행 버튼
  btnRunManual.addEventListener("click", () => {
    const tool = selectManualTool.value;
    if (!tool) {
      showError("실행할 분석 도구를 목록에서 선택해주세요.");
      return;
    }
    const refPeriod = inputManualRefPeriod.value.trim();
    runAnalysisTool(tool, { reference_period: refPeriod });
  });

  // ============================================================================
  // ============================================================================
  // Step 3 -> Step 4: Pandas 도구 실행 (/run) 및 화면 반영
  // ============================================================================
  function applyRunResult(runResult, toolName, params) {
    lastRunResult = runResult;
    console.log(`[RUN] 결과 화면 반영 (도구명: ${runResult.tool}, 사용 행: ${runResult.rows_used}, 제외 행: ${runResult.rows_excluded})`);

    // 메타 정보 표시
    resToolName.textContent = runResult.tool;
    resRefPeriod.textContent = runResult.reference_period || "-";
    resRowsUsed.textContent = `${runResult.rows_used}건`;
    resRowsExcluded.textContent = `${runResult.rows_excluded}건`;
    resUnit.textContent = runResult.unit || "-";

    if (runResult.exclusion_reason) {
      resExclusionReason.textContent = runResult.exclusion_reason;
      resExclusionReasonBox.classList.remove("hidden");
    } else {
      resExclusionReasonBox.classList.add("hidden");
    }

    resCautionText.textContent = runResult.caution || "";

    // 상세 결과 렌더링
    renderResultDetails(runResult.result);

    // 먼저 섹션 표시 및 오픈
    sectionRunResult.classList.remove("hidden");
    sectionExplain.classList.remove("hidden");

    // 부모 컨테이너가 노출된 상태에서 차트 렌더링
    if (runResult.chart_data) {
      setTimeout(() => {
        renderChart(runResult.chart_data);
      }, 50);
    } else {
      chartContainer.classList.add("hidden");
    }

    // 부드러운 스크롤 이동
    sectionRunResult.scrollIntoView({ behavior: "smooth" });
  }

  async function runAnalysisTool(toolName, params) {
    hideError();
    console.log(`[RUN] 도구 실행 시작 (도구명: ${toolName}, 기준시점: ${params.reference_period || "None"})`);

    try {
      const res = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool: toolName, params: params })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "도구 실행 중 오류가 발생했습니다.");
      }

      applyRunResult(data.run_result, toolName, params);

    } catch (err) {
      showError(err.message);
    }
  }

  function renderResultDetails(resultObj) {
    resultContent.innerHTML = "";
    if (!resultObj) return;

    if (resultObj.top_n && resultObj.bottom_n) {
      // 순위 표
      let html = `<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">`;
      html += `<div><h4>상위 ${resultObj.top_n.length}개</h4><ol style="padding-left: 20px;">`;
      resultObj.top_n.forEach(it => {
        html += `<li><strong>${it.label}</strong>: ${it.value}%</li>`;
      });
      html += `</ol></div>`;

      html += `<div><h4>하위 ${resultObj.bottom_n.length}개</h4><ol style="padding-left: 20px;">`;
      resultObj.bottom_n.forEach(it => {
        html += `<li><strong>${it.label}</strong>: ${it.value}%</li>`;
      });
      html += `</ol></div></div>`;
      if (resultObj.gap !== undefined) {
        html += `<p style="margin-top: 10px; color: var(--primary);"><strong>1위와 최하위 격차:</strong> ${resultObj.gap}%p</p>`;
      }
      if (resultObj.highlight_target) {
        html += `<div style="margin-top: 14px; padding: 12px 16px; background: #ecfdf5; border: 1.5px solid #6ee7b7; border-radius: 8px; color: #065f46;">
          <strong>🎯 비교 대상 항목: ${resultObj.highlight_target.label}</strong> &mdash; 순위: <strong>${resultObj.highlight_target.rank}위</strong> (수치: <strong>${resultObj.highlight_target.value}%</strong>)
        </div>`;
      }
      resultContent.innerHTML = html;

    } else if (resultObj.top_growers) {
      // 성장률 표
      let html = `<table class="data-table"><thead><tr><th>순위</th><th>국가/항목</th><th>시작 시점</th><th>종료 시점</th><th>증가량(%p)</th><th>증가율(%)</th></tr></thead><tbody>`;
      resultObj.top_growers.forEach(g => {
        html += `<tr><td>${g.rank}</td><td><strong>${g.label}</strong></td><td>${g.base_val}</td><td>${g.ref_val}</td><td style="color:#f59e0b;font-weight:700;">+${g.diff}</td><td>+${g.pct_change}%</td></tr>`;
      });
      html += `</tbody></table>`;
      resultContent.innerHTML = html;

    } else if (resultObj.distribution) {
      // 분포 표
      let html = `<table class="data-table"><thead><tr><th>구간</th><th>국가 수</th><th>비율</th></tr></thead><tbody>`;
      resultObj.distribution.forEach(d => {
        html += `<tr><td>${d.bin}</td><td>${d.count}개국</td><td>${(d.ratio * 100).toFixed(1)}%</td></tr>`;
      });
      html += `</tbody></table>`;
      resultContent.innerHTML = html;

    } else {
      // 일반 기술통계 딕셔너리 표
      let html = `<table class="data-table"><thead><tr><th>항목</th><th>계산된 수치</th></tr></thead><tbody>`;
      for (const [k, v] of Object.entries(resultObj)) {
        if (typeof v === "object" && v !== null) continue;
        html += `<tr><td>${k}</td><td><strong>${v}</strong></td></tr>`;
      }
      html += `</tbody></table>`;
      resultContent.innerHTML = html;
    }
  }

  // ============================================================================
  // Chart.js 렌더링
  // ============================================================================
  function renderChart(chartData) {
    if (analysisChartInstance) {
      analysisChartInstance.destroy();
    }

    chartContainer.classList.remove("hidden");
    const ctx = analysisChartCanvas.getContext("2d");

    const config = {
      type: chartData.type || "bar",
      data: {
        labels: chartData.labels || [],
        datasets: chartData.datasets || []
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            labels: { font: { family: "Pretendard" } }
          }
        },
        scales: {
          y: {
            beginAtZero: true
          }
        }
      }
    };

    analysisChartInstance = new Chart(ctx, config);
    console.log(`[CHART] 차트 렌더 완료 (차트 종류: ${chartData.type})`);
  }

  btnScrollToExplain.addEventListener("click", () => {
    sectionExplain.scrollIntoView({ behavior: "smooth" });
  });

  // ============================================================================
  // Step 5: Gemini AI 해석 요청 (/explain)
  // ============================================================================
  btnModeB.addEventListener("click", () => {
    activeMode = "B";
    btnModeB.classList.add("active");
    btnModeA.classList.remove("active");
  });

  btnModeA.addEventListener("click", () => {
    activeMode = "A";
    btnModeA.classList.add("active");
    btnModeB.classList.remove("active");
  });

  btnGenerateExplain.addEventListener("click", async () => {
    hideError();
    explainLoading.classList.remove("hidden");
    reportContainer.classList.add("hidden");
    btnGenerateExplain.disabled = true;

    console.log(`[EXPLAIN] 해석 요청 시작 (모드: ${activeMode})`);

    try {
      const res = await fetch("/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: activeMode })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "해석 보고서 생성 중 오류가 발생했습니다.");
      }

      console.log("[EXPLAIN] 응답 수신 완료");

      reportModeBadge.textContent = activeMode === "B" ? "모드 B: 정식 검증 보고서" : "모드 A: 비교용 허술한 보고서";
      reportModeBadge.style.background = activeMode === "B" ? "var(--primary)" : "var(--warning)";
      reportModelBadge.textContent = data.model || "Gemini";

      // Marked.js 마크다운 파싱 렌더링
      reportContent.innerHTML = marked.parse(data.explanation || "");

      reportContainer.classList.remove("hidden");
      reportContainer.scrollIntoView({ behavior: "smooth" });

    } catch (err) {
      showError(err.message);
    } finally {
      explainLoading.classList.add("hidden");
      btnGenerateExplain.disabled = false;
    }
  });

  // 보고서 클립보드 복사
  btnCopyReport.addEventListener("click", () => {
    const textToCopy = reportContent.innerText;
    navigator.clipboard.writeText(textToCopy).then(() => {
      alert("보고서 내용이 클립보드에 복사되었습니다.");
    }).catch(() => {
      showError("클립보드 복사에 실패했습니다.");
    });
  });

  // 초기화 실행
  init();
});
