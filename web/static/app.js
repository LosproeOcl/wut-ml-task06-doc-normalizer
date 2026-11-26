const state = {
  result: null,
  image: null,
  quad: [],
  pending: [],
  dragging: -1,
  moving: false,
  moveStart: null,
  moveOriginal: null,
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
  batchFiles: [],
  batchResults: [],
};

const REVIEW_PAGE_SIZE = 12;

const $ = (id) => document.getElementById(id);
const canvas = $("canvas");
const ctx = canvas.getContext("2d");

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

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
    const handle = state.quad.findIndex(
      ([px, py]) => Math.hypot(px - x, py - y) <= threshold
    );
    if (handle >= 0) {
      state.dragging = handle;
      state.moved = false;
      return;
    }
    if (insidePolygon([x, y], state.quad)) {
      state.moving = true;
      state.moveStart = [x, y];
      state.moveOriginal = state.quad.map((point) => [...point]);
      state.moved = false;
    }
    return;
  }
  if (state.pending.length < 4) {
    state.pending.push([x, y]);
    drawCanvas();
    $("apply-corners").disabled = state.pending.length !== 4;
  }
});

canvas.addEventListener("pointermove", (event) => {
  if (state.moving) {
    const [x, y] = toImagePoint(event);
    const original = state.moveOriginal;
    let dx = x - state.moveStart[0];
    let dy = y - state.moveStart[1];
    const minX = Math.min(...original.map(([px]) => px));
    const maxX = Math.max(...original.map(([px]) => px));
    const minY = Math.min(...original.map(([, py]) => py));
    const maxY = Math.max(...original.map(([, py]) => py));
    dx = Math.max(-minX, Math.min(dx, state.image.naturalWidth - maxX));
    dy = Math.max(-minY, Math.min(dy, state.image.naturalHeight - maxY));
    state.quad = original.map(([px, py]) => [px + dx, py + dy]);
    state.moved = true;
    drawCanvas();
    return;
  }
  if (state.dragging < 0) return;
  state.quad[state.dragging] = toImagePoint(event);
  state.moved = true;
  drawCanvas();
});

canvas.addEventListener("pointerup", () => {
  if (state.moving) {
    state.moving = false;
    $("apply-corners").disabled = state.quad.length !== 4;
    if (state.moved) setStatus("框体已移动，点击“应用四角”重新计算。");
    return;
  }
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

function branchLabel(branch) {
  if (!branch) return "未知";
  if (branch.startsWith("paper-cnn-ensemble")) {
    const count = branch.split("-").pop();
    return `纸质稿 CNN 集成（${count} 模型）`;
  }
  if (branch === "ppt-cnn-exp-cnn-05") return "PPT CNN";
  if (branch === "classic-svm") return "传统基线兜底";
  return branch;
}

function renderRouting(result) {
  const box = $("routing");
  box.innerHTML = "";
  const carrierNames = { ppt: "PPT/幕布", paper: "A4 纸质稿" };
  const carrier = result.carrier || "unknown";
  const carrierName = carrierNames[carrier] || "未判定";
  const probabilities = result.carrier_probabilities || {};
  const confidence = probabilities[carrier];
  const carrierBadge = document.createElement("span");
  carrierBadge.className = "badge";
  carrierBadge.innerHTML = `载体 <strong>${escapeHtml(carrierName)}</strong>${
    typeof confidence === "number" ? ` ${(confidence * 100).toFixed(1)}%` : ""
  }`;
  const branchBadge = document.createElement("span");
  branchBadge.className = "badge";
  branchBadge.innerHTML = `分支 <strong>${escapeHtml(branchLabel(result.branch))}</strong>`;
  box.appendChild(carrierBadge);
  box.appendChild(branchBadge);
}

function showResult(result) {
  state.result = result;
  state.quad = result.quad ? result.quad.map((point) => [...point]) : [];
  state.pending = [];
  $("rectified").hidden = false;
  $("scan").hidden = false;
  const stamp = Date.now();
  $("rectified").src = `/api/results/${result.result_id}/rectified.png?t=${stamp}`;
  $("scan").src = `/api/results/${result.result_id}/scan.png?t=${stamp}`;
  $("pdf-current").disabled = false;
  $("result-card").classList.remove("hidden");
  const batchItem = state.batchFiles.find(
    (item) => item.result && item.result.result_id === result.result_id
  );
  if (batchItem) {
    batchItem.result = result;
    batchItem.status = "完成";
    batchItem.error = "";
    syncBatchSelection();
    renderBatch();
  }
  $("label").textContent = result.label
    ? (result.label === "text" ? "文字" : "公式")
    : "模型未加载";
  renderRouting(result);
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

function selectedResults() {
  return state.batchFiles
    .filter((item) => item.selected && item.result)
    .map((item) => item.result);
}

function syncBatchSelection() {
  state.batchResults = state.batchFiles
    .filter((item) => item.result)
    .map((item) => item.result);
  const selected = selectedResults();
  $("pdf-all").disabled = state.batchResults.length === 0;
  $("pdf-selected").disabled = selected.length === 0;
  $("batch-selected").textContent = `已选 ${selected.length} 张`;
  const max = Math.max(state.batchFiles.length, 1);
  for (const id of ["pdf-range-start", "pdf-range-end"]) {
    const input = $(id);
    input.max = String(max);
    if (Number(input.value) > max) input.value = String(max);
    if (Number(input.value) < 1) input.value = "1";
  }
}

function renderBatch() {
  const list = $("batch-list");
  const hasItems = state.batchFiles.length > 0;
  list.classList.toggle("hidden", !hasItems);
  $("batch-actions").classList.toggle("hidden", !hasItems);
  list.innerHTML = "";
  state.batchFiles.forEach((item) => {
    const card = document.createElement("div");
    card.className = `batch-item${
      item.status === "完成" ? " done" : item.status === "失败" ? " failed" : ""
    }`;
    card.innerHTML = `
      <label class="batch-pick">
        <input type="checkbox" class="batch-check" ${item.selected ? "checked" : ""} />
        选中
      </label>
      <img src="${item.url}" alt="${escapeHtml(item.file.name)}" />
      <div class="batch-meta">
        <div>${escapeHtml(item.file.name)}</div>
        <div class="batch-status">${escapeHtml(item.error || item.status)}${
          item.calibrated ? " · 已校准" : ""
        }</div>
      </div>
      <button type="button" class="batch-remove">移除</button>`;
    card.classList.toggle(
      "active",
      Boolean(
        state.result &&
          item.result &&
          state.result.result_id === item.result.result_id
      )
    );
    card.querySelector(".batch-check").addEventListener("change", (event) => {
      event.stopPropagation();
      item.selected = event.target.checked;
      syncBatchSelection();
    });
    card.addEventListener("click", (event) => {
      if (event.target.closest(".batch-remove, .batch-pick")) return;
      if (!item.result) {
        setStatus("这张图片还没有完成分析。");
        return;
      }
      showResult(item.result);
      setStatus(`已切换到 ${item.file.name}，可拖动四角后应用。`);
    });
    card.querySelector(".batch-remove").addEventListener("click", (event) => {
      event.stopPropagation();
      removeBatch(item.id);
    });
    list.appendChild(card);
  });
  const done = state.batchFiles.filter((item) => item.status === "完成").length;
  $("batch-stats").textContent = `队列 ${state.batchFiles.length} 张，已完成 ${done} 张`;
  syncBatchSelection();
}

async function makeBatchThumbnail(file) {
  try {
    const bitmap = await createImageBitmap(file, {
      resizeWidth: 240,
      resizeQuality: "low",
    });
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    if (bitmap.close) bitmap.close();
    return dataUrl;
  } catch (_) {
    return URL.createObjectURL(file);
  }
}

async function addFiles(fileList) {
  const files = [...fileList].filter(
    (file) =>
      file.type.startsWith("image/") ||
      /\.(jpe?g|png|webp|bmp|heic)$/i.test(file.name)
  );
  if (!files.length) {
    setStatus("请选择图片文件。", true);
    return;
  }
  const room = 20 - state.batchFiles.length;
  if (room <= 0) {
    setStatus("单次最多 20 张。", true);
    return;
  }
  const accepted = files.slice(0, room);
  for (const file of accepted) {
    const url = await makeBatchThumbnail(file);
    state.batchFiles.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      url,
      status: "待分析",
      result: null,
      error: "",
      calibrated: false,
      selected: false,
    });
  }
  renderBatch();
  setStatus(`已加入 ${accepted.length} 张图片。`);
}

function removeBatch(id) {
  const item = state.batchFiles.find((entry) => entry.id === id);
  if (item && item.url.startsWith("blob:")) URL.revokeObjectURL(item.url);
  state.batchFiles = state.batchFiles.filter((entry) => entry.id !== id);
  renderBatch();
}

function clearBatch() {
  state.batchFiles.forEach((item) => {
    if (item.url.startsWith("blob:")) URL.revokeObjectURL(item.url);
  });
  state.batchFiles = [];
  state.batchResults = [];
  for (const id of ["file-input", "camera-input"]) {
    $(id).value = "";
  }
  $("pdf-range-start").value = "1";
  $("pdf-range-end").value = "1";
  renderBatch();
}

function selectRange() {
  const start = Math.max(1, Number($("pdf-range-start").value) || 1);
  const end = Math.min(
    state.batchFiles.length,
    Number($("pdf-range-end").value) || start
  );
  if (end < start) {
    setStatus("区间结束位置不能小于开始位置。", true);
    return;
  }
  state.batchFiles.forEach((item, index) => {
    item.selected = index + 1 >= start && index + 1 <= end;
  });
  renderBatch();
  setStatus(`已选中第 ${start} 到 ${end} 张。`);
}

function selectAll() {
  state.batchFiles.forEach((item) => {
    item.selected = Boolean(item.result);
  });
  renderBatch();
}

function clearSelection() {
  state.batchFiles.forEach((item) => {
    item.selected = false;
  });
  renderBatch();
}

async function analyzeBatch() {
  const button = $("analyze-btn");
  button.disabled = true;
  state.batchFiles.forEach((item) => {
    item.status = "待分析";
    item.error = "";
    item.result = null;
    item.calibrated = false;
  });
  state.batchResults = [];
  let completed = 0;
  try {
    for (const item of state.batchFiles) {
      item.status = "处理中";
      renderBatch();
      setStatus(`批量处理中 ${completed + 1}/${state.batchFiles.length}：${item.file.name}`);
      try {
        const form = new FormData();
        form.append("file", item.file);
        form.append("rectify", $("rectify").checked ? "true" : "false");
        const result = await fetchJSON("/api/analyze", { method: "POST", body: form });
        item.result = result;
        item.status = "完成";
        showResult(result);
        completed += 1;
      } catch (error) {
        item.status = "失败";
        item.error = error.message;
      }
      renderBatch();
    }
    if (completed) {
      setStatus(`批量完成：${completed}/${state.batchFiles.length} 张。`, completed !== state.batchFiles.length);
    } else {
      setStatus("批量处理失败。", true);
    }
  } finally {
    button.disabled = false;
    renderBatch();
  }
}

async function downloadBlob(url, options, filename) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function downloadCurrentPdf() {
  if (!state.result) return;
  try {
    setStatus("生成 PDF…");
    await downloadBlob(
      `/api/pdf/${state.result.result_id}?mode=${$("pdf-mode").value}`,
      {},
      "document.pdf"
    );
    setStatus("PDF 已生成。");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function downloadResultsPdf(results, filename) {
  if (!results.length) {
    setStatus("没有可导出的已完成结果。", true);
    return;
  }
  try {
    setStatus("生成 PDF…");
    await downloadBlob(
      "/api/pdf",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          result_ids: results.map((result) => result.result_id),
          mode: $("pdf-mode").value,
        }),
      },
      filename
    );
    setStatus(`PDF 已生成（${results.length} 页）。`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function downloadSelectedPdf() {
  return downloadResultsPdf(selectedResults(), "document-selected.pdf");
}

async function downloadAllPdf() {
  return downloadResultsPdf(state.batchResults, "document-all.pdf");
}

function openImageModal(src, alt) {
  $("image-modal-img").src = src;
  $("image-modal-img").alt = alt || "查看大图";
  $("image-modal").classList.remove("hidden");
}

function closeImageModal() {
  $("image-modal").classList.add("hidden");
  $("image-modal-img").removeAttribute("src");
}

async function analyze() {
  if (!state.batchFiles.length) {
    setStatus("请先拍照或选择图片。", true);
    return;
  }
  return analyzeBatch();
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
    const item = state.batchFiles.find(
      (entry) => entry.result && entry.result.result_id === result.result_id
    );
    if (item) {
      item.result = result;
      item.calibrated = true;
    }
    showResult(result);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadHealth() {
  try {
    const health = await fetchJSON("/api/health");
    $("health").textContent = health.routing?.routing_ready
      ? "双分支模型已加载"
      : health.model_ready
        ? "分类模型已加载（使用兜底分支）"
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
        <img src="/api/samples/${encodeURIComponent(item.sample_id)}/image" alt="${escapeHtml(item.sample_id)}" loading="lazy">
        ${points.length === 4 ? `
          <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
            <polygon points="${polygon}"></polygon>
            ${handles}
          </svg>` : ""}
      </div>
      <div class="review-meta">
        <strong>${escapeHtml(item.sample_id)}</strong>
        <span class="badge ${item.review_status === "redo" ? "redo" : ""}">${statusText}</span>
        <br>标注人：${escapeHtml(item.annotator || "未分配")}｜原标签：${escapeHtml(item.original_label || "存疑")}
        ${item.redo_reason ? `<br>退回原因：${escapeHtml(item.redo_reason)}` : ""}
      </div>
      <div class="review-actions">
        ${item.review_status === "saved"
          ? `<button type="button" data-redo="${escapeHtml(item.sample_id)}">发回重标</button>`
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
  $("pick-files").addEventListener("click", () => $("file-input").click());
  $("camera-btn").addEventListener("click", () => $("camera-input").click());
  $("file-input").addEventListener("change", () => {
    addFiles($("file-input").files);
    $("file-input").value = "";
  });
  $("camera-input").addEventListener("change", () => {
    addFiles($("camera-input").files);
    $("camera-input").value = "";
  });
  $("rectified").addEventListener("click", () => {
    if ($("rectified").hidden) return;
    openImageModal($("rectified").src, "矫正结果");
  });
  $("scan").addEventListener("click", () => {
    if ($("scan").hidden) return;
    openImageModal($("scan").src, "扫描件");
  });
  $("image-modal-close").addEventListener("click", closeImageModal);
  $("image-modal").addEventListener("click", (event) => {
    if (event.target === $("image-modal")) closeImageModal();
  });
  $("clear-batch").addEventListener("click", clearBatch);
  $("pdf-current").addEventListener("click", downloadCurrentPdf);
  $("pdf-selected").addEventListener("click", downloadSelectedPdf);
  $("pdf-all").addEventListener("click", downloadAllPdf);
  $("pdf-select-range").addEventListener("click", selectRange);
  $("pdf-select-all").addEventListener("click", selectAll);
  $("pdf-select-none").addEventListener("click", clearSelection);
  const dropZone = $("drop-zone");
  ["dragenter", "dragover"].forEach((name) => {
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.add("over");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.remove("over");
    });
  });
  dropZone.addEventListener("drop", (event) => {
    addFiles(event.dataTransfer.files);
  });
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
    if (event.key === "Escape" && !$("image-modal").classList.contains("hidden")) {
      closeImageModal();
      return;
    }
    if ($("annotate-panel").classList.contains("hidden")) return;
    if (event.key === "1") annotate("text");
    if (event.key === "2") annotate("formula");
  });
  window.addEventListener("resize", drawCanvas);
}

async function setupDeviceButtons() {
  const mobile =
    window.matchMedia("(pointer: coarse)").matches ||
    /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  // 手机上相册与文件选择共用系统图片选择器，合并为一个入口。
  $("pick-files").textContent = mobile ? "从相册或文件选择" : "从文件选择";
  let hasCamera = mobile;
  try {
    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices();
      if (devices.length) {
        hasCamera = devices.some((device) => device.kind === "videoinput");
      }
    }
  } catch (_) {
    hasCamera = mobile;
  }
  if (!hasCamera) {
    $("camera-btn").disabled = true;
    $("camera-btn").title = "未检测到摄像头";
  }
}

bindUI();
setupDeviceButtons();
loadHealth();
loadAnnotators().then(() => loadAnnotations());
