(() => {
  "use strict";

  const root = document.querySelector("[data-historico-editor]");
  if (!root) return;

  const canEdit = root.dataset.canEdit === "1";
  const saveUrl = root.dataset.saveUrl || "";
  const csrfToken = document.querySelector("input[name='csrfmiddlewaretoken']")?.value;
  const saveStatus = document.querySelector("[data-save-status]");
  const saveButton = document.querySelector("[data-action='save']");
  const avgOutput = document.querySelector("[data-summary-average]");
  const loadOutput = document.querySelector("[data-summary-load]");
  const alertOutput = document.querySelector("[data-summary-alerts]");
  const logo = document.querySelector("[data-letterhead]");

  let saveTimer = null;
  let saving = false;
  let pendingSave = false;
  const dirtyEditableElements = new WeakSet();

  const cleanText = (element) => (element?.textContent || "").trim();

  function parseNumber(value) {
    const text = String(value ?? "").trim();
    if (!text || /^N\d/i.test(text) || text === "*" || text === "-") return null;
    const match = text.replace(",", ".").match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  }

  function recordIdFromElement(element) {
    return element?.closest("[data-registro-id]")?.dataset.registroId || null;
  }

  function rowsForRecord(id) {
    if (!id) return [];
    return [...root.querySelectorAll(`[data-registro-id="${id}"]`)];
  }

  function firstInRows(rows, selector) {
    for (const row of rows) {
      const found = row.querySelector(selector);
      if (found) return found;
    }
    return null;
  }

  function allInRows(rows, selector) {
    return rows.flatMap((row) => [...row.querySelectorAll(selector)]);
  }

  function thresholdForGrade(rawThreshold, grade) {
    let threshold = parseNumber(rawThreshold);
    if (threshold === null) return grade > 10 ? 60 : 6;
    if (threshold <= 1) return grade > 10 ? threshold * 100 : threshold * 10;
    if (threshold > 10 && grade <= 10) return threshold / 10;
    if (threshold <= 10 && grade > 10) return threshold * 10;
    return threshold;
  }

  function evaluateRecord(recordId, autoStatus = false) {
    const rows = rowsForRecord(recordId);
    if (!rows.length) return false;

    const firstRow = rows[0];
    const thresholdRaw = firstRow.dataset.mediaMinima || "";
    const serie = Number(firstRow.dataset.serie || "0");
    const noteCells = allInRows(rows, "[data-role='nota']");
    const statusCell = firstInRows(rows, "[data-field='resultado']");

    let anyFailed = false;
    let numericCount = 0;

    noteCells.forEach((cell) => {
      const grade = parseNumber(cleanText(cell));
      let failed = false;
      if (grade !== null) {
        numericCount += 1;
        failed = grade < thresholdForGrade(thresholdRaw, grade);
      }
      cell.classList.toggle("alerta-reprovado", failed);
      if (failed) anyFailed = true;
    });

    if (autoStatus && canEdit && statusCell && numericCount > 0) {
      const current = cleanText(statusCell).toUpperCase();
      const locked = new Set(["EM CURSO", "EM CONTINUIDADE"]);
      if (!locked.has(current)) {
        if ((serie === 3 || serie === 5) && anyFailed) {
          statusCell.textContent = "REPROVADO";
        } else {
          statusCell.textContent = "APTO";
        }
      }
    }

    const explicitReprovado = cleanText(statusCell).toUpperCase() === "REPROVADO";
    const warning = anyFailed || explicitReprovado;

    if (statusCell) {
      statusCell.classList.toggle("alerta-reprovado", warning);
      statusCell.dataset.status = warning ? "reprovado" : "aprovado";
    }

    rows.forEach((row) => row.classList.toggle("registro-com-alerta", warning));
    return warning;
  }

  function syncAnnualLoad(recordId, source) {
    const rows = rowsForRecord(recordId);
    const value = cleanText(source);
    allInRows(rows, "[data-field='carga_horaria']").forEach((cell) => {
      if (cell !== source) cell.textContent = value;
    });
  }

  function recalcSummary() {
    const grades = [...root.querySelectorAll("[data-registro-id] [data-role='nota']")]
      .map((cell) => parseNumber(cleanText(cell)))
      .filter((value) => value !== null)
      .map((value) => (value > 10 ? value / 10 : value));

    const loads = [...root.querySelectorAll("[data-role='carga-horaria-total']")]
      .map((cell) => parseNumber(cleanText(cell)))
      .filter((value) => value !== null);

    const alertedIds = new Set(
      [...root.querySelectorAll(".registro-com-alerta[data-registro-id]")]
        .map((row) => row.dataset.registroId)
        .filter(Boolean)
    );

    if (avgOutput) {
      if (grades.length) {
        const avg = grades.reduce((sum, value) => sum + value, 0) / grades.length;
        avgOutput.textContent = avg.toLocaleString("pt-BR", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
      } else {
        avgOutput.textContent = "—";
      }
    }

    if (loadOutput) {
      const total = loads.reduce((sum, value) => sum + value, 0);
      loadOutput.textContent = total
        ? total.toLocaleString("pt-BR", { maximumFractionDigits: 2 })
        : "—";
    }

    if (alertOutput) alertOutput.textContent = String(alertedIds.size);
  }

  function uniqueRecordIds() {
    return [...new Set(
      [...root.querySelectorAll("[data-registro-id]")]
        .map((row) => row.dataset.registroId)
        .filter(Boolean)
    )];
  }

  function collectPayload() {
    const aluno = {};
    root.querySelectorAll("[data-model='aluno'][data-field]").forEach((element) => {
      const optionalDerived = element.dataset.optionalDerived === "1";
      const hasManualValue = element.dataset.hasManualValue === "1";

      if (
        optionalDerived
        && !hasManualValue
        && !dirtyEditableElements.has(element)
      ) {
        return;
      }

      aluno[element.dataset.field] = cleanText(element);
    });

    const registros = uniqueRecordIds().map((id) => {
      const rows = rowsForRecord(id);
      const campos = {};
      allInRows(rows, "[data-model='registro'][data-field]").forEach((element) => {
        campos[element.dataset.field] = cleanText(element);
      });

      const notas = {};
      allInRows(rows, "[data-nota]").forEach((element) => {
        notas[element.dataset.nota] = {
          valor: cleanText(element),
          carga_horaria: "",
        };
      });

      return { id: Number(id), campos, notas };
    });

    const novosRegistros = [...root.querySelectorAll("[data-new-registro-serie]")]
      .map((element) => ({
        serie: Number(element.dataset.newRegistroSerie),
        ano: cleanText(element),
      }))
      .filter((item) => /^\d{4}$/.test(item.ano));

    return { aluno, registros, novos_registros: novosRegistros };
  }

  function setSaveState(message, cssClass = "") {
    if (!saveStatus) return;
    saveStatus.textContent = message;
    saveStatus.className = `save-status ${cssClass}`.trim();
  }

  async function saveNow() {
    if (!canEdit || !saveUrl || !csrfToken) return;
    if (saving) {
      pendingSave = true;
      return;
    }

    saving = true;
    pendingSave = false;
    setSaveState("Salvando…", "is-saving");

    try {
      const response = await fetch(saveUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify(collectPayload()),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.erro || "Não foi possível salvar.");
      }
      root.querySelectorAll("[data-optional-derived='1']").forEach((element) => {
        if (dirtyEditableElements.has(element)) {
          element.dataset.hasManualValue = cleanText(element) ? "1" : "0";
        }
      });
      setSaveState("Alterações salvas", "is-saved");
      if (data.recarregar) {
        window.location.reload();
        return;
      }
    } catch (error) {
      setSaveState(error.message || "Erro ao salvar", "is-error");
    } finally {
      saving = false;
      if (pendingSave) {
        pendingSave = false;
        saveNow();
      }
    }
  }

  function scheduleSave() {
    if (!canEdit) return;
    window.clearTimeout(saveTimer);
    setSaveState("Alterações pendentes");
    saveTimer = window.setTimeout(saveNow, 900);
  }

  function onInput(event) {
    const target = event.target;
    dirtyEditableElements.add(target);
    const recordId = recordIdFromElement(target);

    if (target.matches("[data-role='ano-letivo']")) {
      setSaveState("Alterações pendentes");
      return;
    }

    if (target.matches("[data-role='nota']") && recordId) {
      evaluateRecord(recordId, true);
    } else if (target.matches("[data-field='carga_horaria']") && recordId) {
      syncAnnualLoad(recordId, target);
    } else if (target.matches("[data-field='resultado']") && recordId) {
      evaluateRecord(recordId, false);
    }

    recalcSummary();
    scheduleSave();
  }

  function setupEditableFields() {
    if (!canEdit) return;

    root.querySelectorAll("[contenteditable='true']").forEach((element) => {
      element.addEventListener("input", onInput);
      element.addEventListener("blur", () => {
        window.clearTimeout(saveTimer);
        saveNow();
      });
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && element.dataset.multiline !== "1") {
          event.preventDefault();
          element.blur();
        }
      });
      element.addEventListener("paste", (event) => {
        event.preventDefault();
        const text = event.clipboardData?.getData("text/plain") || "";
        document.execCommand("insertText", false, text);
      });
    });
  }

  function removeMissingYearDiagonals() {
    root.querySelectorAll(".missing-year-diagonal").forEach((element) => {
      element.remove();
    });
  }

  function drawMissingYearDiagonals() {
    removeMissingYearDiagonals();

    const host = root.querySelector(".history-left");
    const table = root.querySelector(".official-history-table");
    if (!host || !table) return;

    const starts = [...table.querySelectorAll("tbody .year-group-start")];
    if (!starts.length) return;

    const runs = [];
    let runStart = null;
    let runEnd = null;

    starts.forEach((row, index) => {
      const missing = row.dataset.emptyYear === "1";
      if (missing) {
        if (runStart === null) runStart = index;
        runEnd = index;
      }

      const isLast = index === starts.length - 1;
      if ((!missing || isLast) && runStart !== null) {
        if (!missing) runEnd = index - 1;
        runs.push([runStart, runEnd]);
        runStart = null;
        runEnd = null;
      }
    });

    const hostRect = host.getBoundingClientRect();
    const tableRect = table.getBoundingClientRect();

    runs.forEach(([startIndex, endIndex]) => {
      const startRow = starts[startIndex];
      const nextStart = starts[endIndex + 1] || null;
      const endRow = nextStart
        ? nextStart.previousElementSibling
        : table.querySelector("tbody tr:last-child");

      const yearCell = startRow.querySelector(".year-cell");
      if (!yearCell || !endRow) return;

      const startRect = startRow.getBoundingClientRect();
      const yearRect = yearCell.getBoundingClientRect();
      const endRect = endRow.getBoundingClientRect();

      const left = yearRect.left - hostRect.left;
      const top = startRect.top - hostRect.top;
      const width = tableRect.right - yearRect.left;
      const height = endRect.bottom - startRect.top;

      if (width <= 0 || height <= 0) return;

      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.classList.add("missing-year-diagonal");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.style.left = `${left}px`;
      svg.style.top = `${top}px`;
      svg.style.width = `${width}px`;
      svg.style.height = `${height}px`;

      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", "0");
      line.setAttribute("y1", "0");
      line.setAttribute("x2", String(width));
      line.setAttribute("y2", String(height));
      svg.appendChild(line);
      host.appendChild(svg);
    });
  }

  async function hydrateLetterheadFallback() {
    if (!logo || !logo.dataset.fallbackB64Url) return;
    if (logo.complete && logo.naturalWidth > 0) return;

    try {
      const response = await fetch(logo.dataset.fallbackB64Url);
      if (!response.ok) return;
      const base64 = (await response.text()).trim();
      if (base64) logo.src = `data:image/jpeg;base64,${base64}`;
    } catch (_) {
      // Mantém o restante do documento disponível mesmo se a imagem falhar.
    }
  }

  uniqueRecordIds().forEach((id) => evaluateRecord(id, false));
  recalcSummary();
  setupEditableFields();
  drawMissingYearDiagonals();

  window.addEventListener("resize", drawMissingYearDiagonals);
  window.addEventListener("beforeprint", drawMissingYearDiagonals);

  saveButton?.addEventListener("click", () => {
    window.clearTimeout(saveTimer);
    saveNow();
  });

  if (logo) {
    logo.addEventListener("error", hydrateLetterheadFallback, { once: true });
    if (logo.complete && logo.naturalWidth === 0) hydrateLetterheadFallback();
  }
})();
