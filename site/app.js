const state = { items: [], current: null };

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function branchLabel(branch) {
  if (!branch) return "未知";
  if (branch.startsWith("paper-cnn-ensemble")) {
    return `纸质稿 CNN 集成（${branch.split("-").pop()} 模型）`;
  }
  if (branch === "ppt-cnn-exp-cnn-05") return "PPT CNN";
  if (branch === "classic-svm") return "传统基线兜底";
  return branch;
}

function renderRouting(item) {
  const box = $("routing");
  box.innerHTML = "";
  const names = { ppt: "PPT/幕布", paper: "A4 纸质稿" };
  const probability = (item.carrier_probabilities || {})[item.carrier];
  const carrier = document.createElement("span");
  carrier.className = "badge";
  carrier.innerHTML = `载体 <strong>${escapeHtml(names[item.carrier] || "未判定")}</strong>${
    typeof probability === "number" ? ` ${(probability * 100).toFixed(1)}%` : ""
  }`;
  const branch = document.createElement("span");
  branch.className = "badge";
  branch.innerHTML = `分支 <strong>${escapeHtml(branchLabel(item.branch))}</strong>`;
  box.appendChild(carrier);
  box.appendChild(branch);
}

function renderProbabilities(probabilities) {
  const box = $("probabilities");
  box.innerHTML = "";
  if (!probabilities) return;
  Object.entries(probabilities).forEach(([name, value]) => {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = `<div class="hint">${name === "text" ? "文字" : "公式"}：${(value * 100).toFixed(1)}%</div>
      <div class="bar"><span style="width:${Math.round(value * 100)}%"></span></div>`;
    box.appendChild(wrapper);
  });
}

function selectItem(item, card) {
  state.current = item;
  document.querySelectorAll(".demo-card").forEach((node) => node.classList.remove("active"));
  card.classList.add("active");
  $("stage-original").src = item.images.original;
  $("stage-rectified").src = item.images.rectified;
  $("stage-scan").src = item.images.scan;
  $("label").textContent = item.label === "formula" ? "公式" : "文字";
  renderRouting(item);
  renderProbabilities(item.probabilities);
  $("meta").textContent = `预计算样张｜状态：${item.status}｜分支：${branchLabel(item.branch)}｜耗时：${item.runtime_ms} ms`;
  $("result-card").classList.remove("hidden");
}

function renderGrid(items) {
  const grid = $("demo-grid");
  grid.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "demo-card";
    card.innerHTML = `<img src="${escapeHtml(item.images.scan)}" alt="${escapeHtml(item.display)}" />
      <strong>${escapeHtml(item.display)}</strong>
      <span>${item.carrier === "ppt" ? "PPT/幕布" : "A4 纸质稿"} · ${item.label === "formula" ? "公式" : "文字"}</span>`;
    card.addEventListener("click", () => selectItem(item, card));
    grid.appendChild(card);
  });
  if (items.length) {
    const first = grid.querySelector(".demo-card");
    selectItem(items[0], first);
  }
}

fetch("demo/index.json")
  .then((response) => {
    if (!response.ok) throw new Error(`加载样张失败：${response.status}`);
    return response.json();
  })
  .then((data) => {
    state.items = data.items || [];
    renderGrid(state.items);
  })
  .catch((error) => {
    $("demo-grid").innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  });
