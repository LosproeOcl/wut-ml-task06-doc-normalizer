const state = {
  result: null,
  image: null,
  quad: [],
  pending: [],
  dragging: -1,
  moved: false,
  annotation: [],
  annotationIndex: 0,
  cornerItems: [],
  cornerIndex: 0,
  cornerImage: null,
  cornerQuad: [],
  cornerPending: [],
  cornerDragging: -1,
  cornerMoving: false,
  cornerMoveStart: null,
  cornerMoveOriginal: null,
  person: "",
  reviewItems: [],
  reviewOffset: 0,
  reviewTotal: 0,
};

const REVIEW_PAGE_SIZE = 12;

const $ = (id) => document.getElementById(id);
const canvas = $("canvas");
const ctx = canvas.getContext("2d");

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return data;
}

function setStatus(text, danger = false) {
  const node = $("status");
  node.textContent = text;
  node.style.color = danger ? "var(--danger)" : "var(--muted)";
}

function drawCanvas() {
  if (!state.image) return;
  const width = canvas.clientWidth || 720;
  const scale = width / state.image.naturalWidth;
  canvas.width = width;
  canvas.height = Math.round(state.image.naturalHeight * scale);
  ctx.drawImage(state.image, 0, 0, canvas.width, canvas.height);

  const points = state.quad.length ? state.quad : state.pending;
  if (points.length) {
    ctx.beginPath();
    points.forEach(([x, y], index) => {
      const px = x * scale;
      const py = y * scale;
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    if (points.length === 4) ctx.closePath();
    ctx.strokeStyle = "#3354aa";
    ctx.lineWidth = 3;
    ctx.stroke();
  }
  points.forEach(([x, y], index) => {
    const px = x * scale;
    const py = y * scale;
    ctx.beginPath();
    ctx.arc(px, py, 8, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.strokeStyle = "#3354aa";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#3354aa";
    ctx.font = "12px sans-serif";
    ctx.fillText(String(index + 1), px + 10, py - 8);
  });
}

function toImagePoint(event) {
  const rect = canvas.getBoundingClientRect();
  const scale = canvas.width / state.image.naturalWidth;
  const x = (event.clientX - rect.left) * (canvas.width / rect.width) / scale;
  const y = (event.clientY - rect.top) * (canvas.height / rect.height) / scale;
  return [Math.max(0, Math.min(x, state.image.naturalWidth)),
          Math.max(0, Math.min(y, state.image.naturalHeight))];
}

canvas.addEventListener("pointerdown", (event) => {
  if (!state.image) return;
  canvas.setPointerCapture(event.pointerId);
  const [x, y] = toImagePoint(event);
  const threshold = 16 * (state.image.naturalWidth / canvas.width);
  if (state.quad.length) {
    state.dragging = state.quad.findIndex(
      ([px, py]) => Math.hypot(px - x, py - y) <= threshold
    );
    state.moved = false;
    return;
  }
  if (state.pending.length < 4) {
    state.pending.push([x, y]);
    drawCanvas();
    $("apply-corners").disabled = state.pending.length !== 4;
  }
});

canvas.addEventListener("pointermove", (event) => {
  if (state.dragging < 0) return;
  state.quad[state.dragging] = toImagePoint(event);
  state.moved = true;
  drawCanvas();
});

canvas.addEventListener("pointerup", () => {
  if (state.dragging >= 0) {
    state.dragging = -1;
    $("apply-corners").disabled = state.quad.length !== 4;
    if (state.moved) setStatus("四角已调整，点击“应用四角”重新计算。");
  }
});

function probabilityBars(probabilities) {
  const box = $("probabilities");
  box.innerHTML = "";
  if (!probabilities) return;
  Object.entries(probabilities).forEach(([name, value]) => {
    const label = name === "text" ? "文字" : "公式";
    const wrapper = document.createElement("div");
    wrapper.innerHTML = `<div class="hint">${label}：${(value * 100).toFixed(1)}%</div>
      <div class="bar"><span style="width:${Math.round(value * 100)}%"></span></div>`;
    box.appendChild(wrapper);
  });
}

function showResult(result) {
  state.result = result;
  state.quad = result.quad ? result.quad.map((point) => [...point]) : [];
  state.pending = [];
  $("rectified").hidden = false;
  $("enhanced").hidden = false;
  $("rectified").src = `/api/results/${result.result_id}/rectified.png`;
  $("enhanced").src = `/api/results/${result.result_id}/enhanced.png`;
  $("result-card").classList.remove("hidden");
  $("label").textContent = result.label
    ? (result.label === "text" ? "文字" : "公式")
    : "模型未加载";
  probabilityBars(result.probabilities);
  $("meta").textContent =
    `状态：${result.status}｜方式：${result.method}｜耗时：${result.runtime_ms} ms`;
  $("apply-corners").disabled = result.quad === null;

  const image = new Image();
  image.onload = () => {
    state.image = image;
    drawCanvas();
  };
  image.src = `/api/results/${result.result_id}/original.png?t=${Date.now()}`;

  if (result.status === "rectify_failed") {
    setStatus("未检出文档四边形，请在原图上依次点击四个顶点后应用。", true);
  } else {
    setStatus("分析完成。");
  }
}

async function analyze() {
  const button = $("analyze-btn");
  button.disabled = true;
  setStatus("处理中…");
  try {
    const form = new FormData();
    const file = $("file-input").files[0];
    if (file) form.append("file", file);
    else if ($("sample-select").value) form.append("sample_id", $("sample-select").value);
    else throw new Error("请上传图片或选择样本");
    form.append("rectify", $("rectify").checked ? "true" : "false");
    form.append("enhance", $("enhance").checked ? "true" : "false");
    const result = await fetchJSON("/api/analyze", { method: "POST", body: form });
    showResult(result);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function applyCorners() {
  if (!state.result) return;
  const points = state.quad.length ? state.quad : state.pending;
  if (points.length !== 4) return;
  setStatus("重新计算中…");
  try {
    const result = await fetchJSON(
      `/api/analyze/${state.result.result_id}/corners`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ points }),
      }
    );
    showResult(result);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadSamples() {
  try {
    const data = await fetchJSON("/api/samples?limit=100");
    const select = $("sample-select");
    data.items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.sample_id;
      option.textContent = `${item.sample_id}（${item.split}，${item.label || "存疑"}）`;
      select.appendChild(option);
    });
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadHealth() {
  try {
    const health = await fetchJSON("/api/health");
    $("health").textContent = health.model_ready
      ? "分类模型已加载"
      : "未找到分类模型，仅展示预处理";
  } catch (_) {
    $("health").textContent = "服务状态未知";
  }
}

async function loadAnnotators() {
  try {
    const data = await fetchJSON("/api/annotators");
    const select = $("person-select");
    select.innerHTML = '<option value="">全部成员</option>';
    data.members.forEach((member) => {
      const option = document.createElement("option");
      option.value = member.name;
      option.textContent = `${member.name}（分配 ${member.assigned}）`;
      select.appendChild(option);
    });
    const names = data.members.map((member) => member.name);
    const reviewSelect = $("review-assignee");
    const previousReview = reviewSelect.value;
    reviewSelect.innerHTML = '<option value="">全部成员</option>';
    data.members.forEach((member) => {
      const option = document.createElement("option");
      option.value = member.name;
      option.textContent = `${member.name}（已保存 ${member.corners}）`;
      reviewSelect.appendChild(option);
    });
    reviewSelect.value = names.includes(previousReview) ? previousReview : "";
    const saved = localStorage.getItem("t06-person");
    state.person = saved && names.includes(saved) ? saved : (names[0] || "");
    select.value = state.person;
    state.annotatorData = data.members;
    updatePersonStats();
  } catch (error) {
    $("person-stats").textContent = error.message;
  }
}

function updatePersonStats() {
  const member = (state.annotatorData || []).find((item) => item.name === state.person);
  $("person-stats").textContent = member
    ? `已分配 ${member.assigned} · 四角 ${member.corners} · 标签 ${member.labels}`
    : "未选择成员时显示全部训练样本";
}

async function loadAnnotations() {
  try {
    const suffix = state.person ? `&assignee=${encodeURIComponent(state.person)}` : "";
    const data = await fetchJSON(`/api/annotations?limit=50&only_unlabeled=true${suffix}`);
    state.annotation = data.items;
    state.annotationIndex = 0;
    renderAnnotation(data.stats);
  } catch (error) {
    $("anno-stats").textContent = error.message;
  }
}

function renderAnnotation(stats) {
  if (stats) {
    $("anno-stats").textContent =
      `训练集 ${stats.train_total} 张，已校正 ${stats.annotated} 张`;
  }
  const item = state.annotation[state.annotationIndex];
  const empty = $("anno-empty");
  if (!item) {
    empty.classList.remove("hidden");
    $("anno-image").removeAttribute("src");
    $("anno-id").textContent = "";
    $("anno-original").textContent = "";
    return;
  }
  empty.classList.add("hidden");
  $("anno-image").src = `/api/samples/${encodeURIComponent(item.sample_id)}/image`;
  $("anno-id").textContent = item.sample_id;
  $("anno-original").textContent = item.original_label || "存疑";
}

async function annotate(label) {
  const item = state.annotation[state.annotationIndex];
  if (!item) return;
  try {
    const stats = await fetchJSON("/api/annotations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sample_id: item.sample_id,
        label,
        annotator: state.person || "web",
      }),
    });
    state.annotationIndex += 1;
    renderAnnotation(stats);
  } catch (error) {
    $("anno-stats").textContent = error.message;
  }
}

async function loadCorners() {
  try {
    $("corner-stats").textContent = "载入待标注样本…";
    const suffix = state.person ? `&assignee=${encodeURIComponent(state.person)}` : "";
    const data = await fetchJSON(`/api/corners?limit=20&only_unannotated=true${suffix}`);
    state.cornerItems = data.items;
    state.cornerIndex = 0;
    renderCorner(data.stats);
  } catch (error) {
    $("corner-stats").textContent = error.message;
  }
}

function renderCorner(stats) {
  if (stats) {
    $("corner-stats").textContent =
      `训练集 ${stats.train_total} 张，已保存四角 ${stats.annotated} 张`;
  }
  const item = state.cornerItems[state.cornerIndex];
  const empty = $("corner-empty");
  if (!item) {
    empty.classList.remove("hidden");
    $("corner-id").textContent = "";
    $("corner-label").textContent = "";
    $("corner-source").textContent = "";
    $("corner-reason").classList.add("hidden");
    $("corner-confirm").disabled = true;
    return;
  }
  empty.classList.add("hidden");
  $("corner-id").textContent = item.sample_id;
  $("corner-label").textContent = item.original_label || "存疑";
  $("corner-source").textContent =
    item.source === "auto" ? "自动检测建议"
    : item.source === "manual" ? "已保存"
    : item.source === "redo" ? "审查退回，需重新标注"
    : "未检出";
  const reasonNode = $("corner-reason");
  reasonNode.textContent = item.redo_reason ? `退回原因：${item.redo_reason}` : "";
  reasonNode.classList.toggle("hidden", !item.redo_reason);
  state.cornerQuad = item.points
    ? item.points.map(([x, y]) => {
        const [width, height] = item.resolution.split("x").map(Number);
        return [
          Math.max(0, Math.min(x, width - 1)),
          Math.max(0, Math.min(y, height - 1)),
        ];
      })
    : [];
  state.cornerPending = [];
  state.cornerDragging = -1;
  state.cornerMoving = false;
  $("corner-confirm").disabled = state.cornerQuad.length !== 4;

  const image = new Image();
  image.onload = () => {
    state.cornerImage = image;
    drawCornerCanvas();
  };
  image.src = `/api/samples/${encodeURIComponent(item.sample_id)}/image?t=${Date.now()}`;
}

function drawCornerCanvas() {
  const canvas = $("corner-canvas");
  const ctx = canvas.getContext("2d");
  if (!state.cornerImage) return;
  const width = canvas.clientWidth || 720;
  const scale = width / state.cornerImage.naturalWidth;
  canvas.width = width;
  canvas.height = Math.round(state.cornerImage.naturalHeight * scale);
  ctx.drawImage(state.cornerImage, 0, 0, canvas.width, canvas.height);

  const points = state.cornerQuad.length ? state.cornerQuad : state.cornerPending;
  if (points.length) {
    ctx.beginPath();
    points.forEach(([x, y], index) => {
      const px = x * scale;
      const py = y * scale;
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    if (points.length === 4) ctx.closePath();
    ctx.strokeStyle = "#3354aa";
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  points.forEach(([x, y], index) => {
    const px = x * scale;
    const py = y * scale;
    ctx.beginPath();
    ctx.arc(px, py, 7, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.strokeStyle = "#3354aa";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#3354aa";
    ctx.font = "12px sans-serif";
    ctx.fillText(String(index + 1), px + 10, py - 8);
  });
}

function cornerPoint(event) {
  const canvas = $("corner-canvas");
  const rect = canvas.getBoundingClientRect();
  const scale = canvas.width / state.cornerImage.naturalWidth;
  const x = (event.clientX - rect.left) * (canvas.width / rect.width) / scale;
  const y = (event.clientY - rect.top) * (canvas.height / rect.height) / scale;
  return [
    Math.max(0, Math.min(x, state.cornerImage.naturalWidth)),
    Math.max(0, Math.min(y, state.cornerImage.naturalHeight)),
  ];
}

function clampCornerPoint([x, y]) {
  return [
    Math.max(0, Math.min(x, state.cornerImage.naturalWidth - 1)),
    Math.max(0, Math.min(y, state.cornerImage.naturalHeight - 1)),
  ];
}

function insidePolygon(point, polygon) {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function bindCornerCanvas() {
  const canvas = $("corner-canvas");
  canvas.addEventListener("pointerdown", (event) => {
    if (!state.cornerImage) return;
    canvas.setPointerCapture(event.pointerId);
    const [x, y] = cornerPoint(event);
    const threshold = 16 * (state.cornerImage.naturalWidth / canvas.width);
    if (state.cornerQuad.length === 4) {
      const handle = state.cornerQuad.findIndex(
        ([px, py]) => Math.hypot(px - x, py - y) <= threshold
      );
      if (handle >= 0) {
        state.cornerDragging = handle;
        return;
      }
      if (insidePolygon([x, y], state.cornerQuad)) {
        state.cornerMoving = true;
        state.cornerMoveStart = [x, y];
        state.cornerMoveOriginal = state.cornerQuad.map((point) => [...point]);
        return;
      }
    }
    if (state.cornerPending.length < 4) {
      state.cornerPending.push([x, y]);
      drawCornerCanvas();
      $("corner-confirm").disabled = state.cornerPending.length !== 4;
    }
  });
  canvas.addEventListener("pointermove", (event) => {
    if (state.cornerMoving) {
      const [x, y] = cornerPoint(event);
      const dx = x - state.cornerMoveStart[0];
      const dy = y - state.cornerMoveStart[1];
      state.cornerQuad = state.cornerMoveOriginal.map(([px, py]) =>
        clampCornerPoint([px + dx, py + dy])
      );
      drawCornerCanvas();
      return;
    }
    if (state.cornerDragging < 0) return;
    state.cornerQuad[state.cornerDragging] = clampCornerPoint(cornerPoint(event));
    drawCornerCanvas();
  });
  canvas.addEventListener("pointerup", () => {
    if (state.cornerDragging >= 0) {
      state.cornerDragging = -1;
      $("corner-confirm").disabled = state.cornerQuad.length !== 4;
    }
    if (state.cornerMoving) {
      state.cornerMoving = false;
      $("corner-confirm").disabled = state.cornerQuad.length !== 4;
    }
  });
  window.addEventListener("resize", drawCornerCanvas);
}

async function confirmCorner() {
  const item = state.cornerItems[state.cornerIndex];
  if (!item) return;
  const points = state.cornerQuad.length ? state.cornerQuad : state.cornerPending;
  if (points.length !== 4) return;
  $("corner-confirm").disabled = true;
  try {
    const stats = await fetchJSON("/api/corners", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sample_id: item.sample_id,
        points,
        annotator: state.person || "web",
      }),
    });
    state.cornerIndex += 1;
    renderCorner(stats);
  } catch (error) {
    $("corner-stats").textContent = error.message;
    $("corner-confirm").disabled = false;
  }
}

function reviewQuery() {
  const params = new URLSearchParams({
    limit: String(REVIEW_PAGE_SIZE),
    offset: String(state.reviewOffset),
  });
  const assignee = $("review-assignee").value;
  const status = $("review-status").value;
  if (assignee) params.set("assignee", assignee);
  if (status) params.set("status", status);
  return params.toString();
}

async function loadReview(reset = true) {
  if (reset) state.reviewOffset = 0;
  try {
    $("review-stats").textContent = "载入标注记录…";
    const data = await fetchJSON(`/api/review/corners?${reviewQuery()}`);
    state.reviewItems = data.items;
    state.reviewTotal = data.total;
    if (data.stats) {
      $("review-stats").textContent =
        `已保存 ${data.stats.saved} · 已退回 ${data.stats.redo} · 未标注 ${data.stats.unannotated}`;
    }
    renderReview();
  } catch (error) {
    $("review-stats").textContent = error.message;
  }
}

function renderReview() {
  const grid = $("review-grid");
  grid.innerHTML = "";
  if (!state.reviewItems.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "当前筛选条件下没有样本。";
    grid.appendChild(empty);
    $("review-page").textContent = "";
    $("review-prev").disabled = true;
    $("review-next").disabled = true;
    return;
  }
  state.reviewItems.forEach((item) => {
    const [width, height] = item.resolution.split("x").map(Number);
    const card = document.createElement("div");
    card.className = "review-card";
    const points = item.points || [];
    const polygon = points.map(([x, y]) => `${x},${y}`).join(" ");
    const handleRadius = Math.max(width, height) * 0.008;
    const handles = points
      .map(([x, y], index) =>
        `<circle cx="${x}" cy="${y}" r="${handleRadius}" class="handle" data-index="${index + 1}"></circle>`)
      .join("");
    const statusText =
      item.review_status === "saved" ? "已保存"
      : item.review_status === "redo" ? "已退回" : "未标注";
    card.innerHTML = `
      <div class="review-frame">
        <img src="/api/samples/${encodeURIComponent(item.sample_id)}/image" alt="${item.sample_id}" loading="lazy">
        ${points.length === 4 ? `
          <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
            <polygon points="${polygon}"></polygon>
            ${handles}
          </svg>` : ""}
      </div>
      <div class="review-meta">
        <strong>${item.sample_id}</strong>
        <span class="badge ${item.review_status === "redo" ? "redo" : ""}">${statusText}</span>
        <br>标注人：${item.annotator || "未分配"}｜原标签：${item.original_label || "存疑"}
        ${item.redo_reason ? `<br>退回原因：${item.redo_reason}` : ""}
      </div>
      <div class="review-actions">
        ${item.review_status === "saved"
          ? `<button type="button" data-redo="${item.sample_id}">发回重标</button>`
          : item.review_status === "redo"
            ? `<span class="hint">等待该成员重新标注</span>`
            : `<span class="hint">尚未提交四角</span>`}
      </div>`;
    grid.appendChild(card);
  });
  grid.querySelectorAll("[data-redo]").forEach((button) => {
    button.addEventListener("click", () => sendBackCorner(button.dataset.redo, button));
  });

  const start = state.reviewOffset + 1;
  const end = state.reviewOffset + state.reviewItems.length;
  $("review-page").textContent = `${start}–${end} / ${state.reviewTotal}`;
  $("review-prev").disabled = state.reviewOffset <= 0;
  $("review-next").disabled = state.reviewOffset + REVIEW_PAGE_SIZE >= state.reviewTotal;
}

async function sendBackCorner(sampleId, button) {
  const input = window.prompt("退回原因（留空使用默认说明）", "");
  if (input === null) return;
  const reason = input.trim() || "审查退回：四角范围不符合整页口径";
  button.disabled = true;
  try {
    await fetchJSON(`/api/review/corners/${encodeURIComponent(sampleId)}/redo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    });
    loadReview(false);
  } catch (error) {
    $("review-stats").textContent = error.message;
    button.disabled = false;
  }
}

function bindUI() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", (event) => {
      event.preventDefault();
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.dataset.tab;
      const panels = {
        analyze: "analyze-panel",
        annotate: "annotate-panel",
        corners: "corner-panel",
        review: "review-panel",
      };
      Object.entries(panels).forEach(([key, id]) => {
        $(id).classList.toggle("hidden", key !== target);
      });
      $("person-bar").classList.toggle("hidden", target === "analyze" || target === "review");
      if (target === "annotate") loadAnnotations();
      if (target === "corners") loadCorners();
      if (target === "review") loadReview(true);
    });
  });
  $("analyze-btn").addEventListener("click", analyze);
  $("apply-corners").addEventListener("click", applyCorners);
  $("file-input").addEventListener("change", () => { $("sample-select").value = ""; });
  $("sample-select").addEventListener("change", () => { $("file-input").value = ""; });
  $("person-select").addEventListener("change", () => {
    state.person = $("person-select").value;
    localStorage.setItem("t06-person", state.person);
    updatePersonStats();
    if (!$("annotate-panel").classList.contains("hidden")) loadAnnotations();
    if (!$("corner-panel").classList.contains("hidden")) loadCorners();
  });
  $("reload-anno").addEventListener("click", loadAnnotations);
  $("anno-skip").addEventListener("click", () => {
    state.annotationIndex += 1;
    renderAnnotation(null);
  });
  bindCornerCanvas();
  $("corner-confirm").addEventListener("click", confirmCorner);
  $("corner-skip").addEventListener("click", () => {
    state.cornerIndex += 1;
    renderCorner(null);
  });
  $("review-reload").addEventListener("click", () => loadReview(true));
  $("review-assignee").addEventListener("change", () => loadReview(true));
  $("review-status").addEventListener("change", () => loadReview(true));
  $("review-prev").addEventListener("click", () => {
    state.reviewOffset = Math.max(0, state.reviewOffset - REVIEW_PAGE_SIZE);
    loadReview(false);
  });
  $("review-next").addEventListener("click", () => {
    state.reviewOffset += REVIEW_PAGE_SIZE;
    loadReview(false);
  });
  document.querySelectorAll("[data-label]").forEach((button) => {
    button.addEventListener("click", () => annotate(button.dataset.label));
  });
  document.addEventListener("keydown", (event) => {
    if ($("annotate-panel").classList.contains("hidden")) return;
    if (event.key === "1") annotate("text");
    if (event.key === "2") annotate("formula");
  });
  window.addEventListener("resize", drawCanvas);
}

bindUI();
loadSamples();
loadHealth();
loadAnnotators().then(() => loadAnnotations());
