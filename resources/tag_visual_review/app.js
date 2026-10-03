"use strict";

const $ = (id) => document.getElementById(id);
const pageSize = 72;
const controls = ["search", "group", "status", "category", "sort", "only-selected", "dark-preview"];
let catalogue = null;
let reviews = {};
let token = "";
let stateVersion = 0;
let page = 1;
let detailItem = null;
let loading = false;
let noteDirty = false;
let toastTimer;
const pending = new Set();
const pendingChoices = new Map();
const itemCards = new Map();

function savedStatus(message = "已保存到本机", state = "") {
  $("save-status").textContent = message;
  $("save-status").className = state;
}

function toast(message) {
  if ($("detail").open) {
    $("note-status").textContent = message;
    return;
  }
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 6500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    cache: "no-store",
    credentials: "same-origin",
    headers: { "X-Review-Token": token, ...options.headers },
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || "本机后台暂时不可用。");
    error.details = body;
    error.status = response.status;
    throw error;
  }
  return body;
}

function currentReview(id) {
  return reviews[id] || { needs_rework: false, note: "", row_version: 0 };
}

function formatNumber(value) { return value.toLocaleString("zh-CN"); }

function updateCounts(selectedCount) {
  $("total-count").textContent = formatNumber(catalogue.total);
  $("selected-count").textContent = formatNumber(selectedCount);
  $("export").disabled = loading || pending.size > 0;
}

function imageUrl(item, small = false) {
  const theme = $("dark-preview").checked ? "dark" : "light";
  return `/icons/${item.id}.svg?theme=${theme}&variant=${small ? "small" : "large"}&revision=${item.icon_revision}`;
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function statusLabel(status) {
  return catalogue.statuses.find((entry) => entry.value === status)?.label || status;
}

function updateCard(item) {
  const card = itemCards.get(item.id);
  if (!card) return;
  const review = currentReview(item.id);
  const displayedChoice = pendingChoices.get(item.id) ?? review.needs_rework;
  card.element.classList.toggle("selected", displayedChoice);
  card.element.classList.toggle("saving", pending.has(item.id));
  card.checkbox.checked = displayedChoice;
  card.checkbox.disabled = pending.has(item.id);
  const changed = review.needs_rework && review.icon_revision !== item.icon_revision;
  card.note.textContent = changed ? "图示已更新，旧标记仍保留" : (review.note ? "已附重做原因" : "");
  card.note.hidden = !card.note.textContent;
}

function createCard(item) {
  const article = makeElement("article", "card");
  article.dataset.id = item.id;
  const top = makeElement("div", "card-top");
  const badge = makeElement("span", "badge", statusLabel(item.status));
  badge.classList.toggle("category-only", item.status === "category_only");
  const small = makeElement("img", "small-preview");
  small.width = small.height = 24;
  small.alt = "";
  small.title = "列表图标 · 24 × 24";
  small.loading = "lazy";
  small.src = imageUrl(item, true);
  top.append(badge, small);
  const iconButton = makeElement("button", "icon-button");
  iconButton.type = "button";
  iconButton.setAttribute("aria-label", `放大 ${item.name} 图示`);
  const image = makeElement("img");
  image.width = image.height = 160;
  image.alt = `${item.label_zh}示意图`;
  image.loading = "lazy";
  image.src = imageUrl(item);
  image.addEventListener("error", () => {
    image.alt = "图示载入失败，可勾选重做";
    small.hidden = true;
  });
  iconButton.append(image);
  iconButton.addEventListener("click", () => openDetail(item));
  const name = makeElement("h3", "card-name", item.name);
  const label = makeElement("p", "card-label", item.label_zh);
  const explanation = makeElement("p", "card-explanation", item.explanation_zh);
  const checkLabel = makeElement("label", "review-check");
  const checkbox = makeElement("input");
  checkbox.type = "checkbox";
  checkbox.setAttribute("aria-label", `${item.name} 需要重做`);
  checkbox.addEventListener("change", () => saveReview(item, checkbox.checked));
  checkLabel.append(checkbox, makeElement("span", "", "需要重做"));
  const note = makeElement("p", "note-chip");
  article.append(top, iconButton, name, label, explanation, checkLabel, note);
  itemCards.set(item.id, { element: article, checkbox, note });
  updateCard(item);
  return article;
}

function filteredItems() {
  const query = $("search").value.trim().toLocaleLowerCase().replaceAll("_", " ");
  const group = $("group").value;
  const status = $("status").value;
  const category = $("category").value;
  const selected = $("only-selected").checked;
  const results = catalogue.items.filter((item) =>
    (!group || item.group === group) && (!status || item.status === status) &&
    (!category || item.category === category) && (!selected || currentReview(item.id).needs_rework) &&
    (!query || `${item.name} ${item.label_zh} ${item.explanation_zh}`.toLocaleLowerCase().replaceAll("_", " ").includes(query))
  );
  const sort = $("sort").value;
  if (sort === "name") results.sort((a, b) => a.name.localeCompare(b.name, "en") || a.category.localeCompare(b.category));
  else if (sort === "group") results.sort((a, b) => a.group.localeCompare(b.group) || b.count - a.count || a.name.localeCompare(b.name, "en"));
  return results;
}

function rememberPosition() {
  try {
    const filters = Object.fromEntries(controls.map((id) => [id, $(id).type === "checkbox" ? $(id).checked : $(id).value]));
    localStorage.setItem("tag-review-position", JSON.stringify({ page, filters }));
  } catch { /* Browser preferences are optional; feedback lives in the backend. */ }
}

function restorePosition() {
  try {
    const preferences = JSON.parse(localStorage.getItem("tag-review-position") || "null");
    if (!preferences) return;
    for (const id of controls) {
      const value = preferences.filters?.[id];
      if ($(id).type === "checkbox" && typeof value === "boolean") $(id).checked = value;
      else if (typeof value === "string") {
        if ($(id).tagName !== "SELECT" || [...$(id).options].some((option) => option.value === value)) $(id).value = value;
      }
    }
    if (Number.isInteger(preferences.page) && preferences.page > 0) page = preferences.page;
  } catch { /* Ignore unavailable or obsolete preferences. */ }
}

function render() {
  if (!catalogue) return;
  const items = filteredItems();
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  page = Math.min(Math.max(page, 1), pages);
  const start = (page - 1) * pageSize;
  itemCards.clear();
  const fragment = document.createDocumentFragment();
  for (const item of items.slice(start, start + pageSize)) fragment.append(createCard(item));
  $("gallery").replaceChildren(fragment);
  $("gallery").setAttribute("aria-busy", "false");
  $("empty").hidden = items.length > 0;
  $("result-info").textContent = items.length
    ? `显示 ${formatNumber(start + 1)}–${formatNumber(Math.min(start + pageSize, items.length))}，共 ${formatNumber(items.length)} 项`
    : "没有符合条件的图示";
  for (const suffix of ["", "-top"]) {
    $("page-info" + suffix).textContent = `${page} / ${pages}`;
    $("previous" + suffix).disabled = page <= 1;
    $("next" + suffix).disabled = page >= pages;
  }
  document.body.classList.toggle("dark-preview", $("dark-preview").checked);
  rememberPosition();
}

function syncDetail(resetNote = false) {
  if (!detailItem) return;
  const review = currentReview(detailItem.id);
  const busy = pending.has(detailItem.id);
  $("detail-check").checked = pendingChoices.get(detailItem.id) ?? review.needs_rework;
  $("detail-check").disabled = busy;
  $("detail-note").disabled = busy || !review.needs_rework;
  $("save-note").disabled = busy || !review.needs_rework;
  if (resetNote || !noteDirty) $("detail-note").value = review.note;
  $("detail-image").src = imageUrl(detailItem);
}

function openDetail(item) {
  detailItem = item;
  noteDirty = false;
  $("detail-name").textContent = item.name;
  $("detail-label").textContent = item.label_zh;
  $("detail-explanation").textContent = item.explanation_zh;
  $("detail-reason").textContent = item.reason;
  $("detail-reason").hidden = !item.reason;
  $("detail-badge").textContent = statusLabel(item.status);
  $("detail-badge").classList.toggle("category-only", item.status === "category_only");
  $("detail-image").alt = `${item.label_zh}放大示意图`;
  $("detail-check").setAttribute("aria-label", `${item.name} 需要重做`);
  const review = currentReview(item.id);
  $("note-status").textContent = review.note ? "已保存的原因" : (review.needs_rework ? "填写后点击保存原因" : "先勾选需要重做，再补充原因");
  syncDetail(true);
  $("detail").showModal();
}

async function saveReview(item, needsRework, note) {
  if (pending.has(item.id)) return;
  const previous = currentReview(item.id);
  let needsRefresh = false;
  pending.add(item.id);
  pendingChoices.set(item.id, needsRework);
  updateCard(item);
  syncDetail();
  savedStatus("正在保存…", "saving");
  $("export").disabled = true;
  const payload = { id: item.id, needs_rework: needsRework, expected_version: previous.row_version };
  if (note !== undefined) payload.note = note;
  try {
    const result = await api("/api/review", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    reviews[item.id] = result.review;
    if (result.version >= stateVersion) {
      stateVersion = result.version;
      updateCounts(result.selected_count);
    }
    if (note !== undefined && detailItem?.id === item.id) {
      noteDirty = false;
      $("note-status").textContent = "原因已保存到本机";
    }
    if (result.warning) toast(result.warning);
    savedStatus(result.warning || (pending.size > 1 ? "正在保存…" : "已保存到本机"), result.warning ? "failed" : "");
  } catch (error) {
    if (error.status === 409 && error.details.current) {
      reviews[item.id] = error.details.current;
      needsRefresh = true;
    }
    // Restore the last confirmed backend value rather than claiming a failed save succeeded.
    savedStatus("保存失败，请重试", "failed");
    toast(error.message || "保存失败，已恢复之前的选择。请重试。");
  } finally {
    pending.delete(item.id);
    pendingChoices.delete(item.id);
    updateCard(item);
    syncDetail();
    $("export").disabled = pending.size > 0;
    if ($("only-selected").checked) render();
    if (needsRefresh) await refreshState().catch(() => {});
  }
}

async function refreshState() {
  const result = await api("/api/state");
  if (pending.size > 0 || result.version < stateVersion) return;
  const changed = result.version !== stateVersion;
  reviews = result.reviews;
  stateVersion = result.version;
  updateCounts(result.selected_count);
  if (changed) {
    if ($("only-selected").checked) render();
    else for (const item of catalogue.items) if (itemCards.has(item.id)) updateCard(item);
    syncDetail();
  }
}

async function initialise() {
  if (loading) return;
  loading = true;
  $("error").hidden = true;
  $("export").disabled = true;
  savedStatus("正在连接本机后台…");
  try {
    const session = await api("/api/bootstrap");
    token = session.token;
    const [loadedCatalogue, state] = await Promise.all([api("/api/catalog"), api("/api/state")]);
    catalogue = loadedCatalogue;
    reviews = state.reviews;
    stateVersion = state.version;
    for (const field of ["group", "status", "category"]) {
      const select = $(field);
      while (select.options.length > 1) select.remove(1);
      const list = catalogue[{ group: "groups", status: "statuses", category: "categories" }[field]];
      for (const entry of list) select.add(new Option(`${entry.label} (${formatNumber(entry.count)})`, entry.value));
    }
    restorePosition();
    updateCounts(state.selected_count);
    render();
    savedStatus("已保存到本机");
  } catch (error) {
    $("error-message").textContent = error.message || "无法连接本机后台，请检查网站是否已启动。";
    $("error").hidden = false;
    savedStatus("无法连接本机后台", "failed");
  } finally {
    loading = false;
    $("export").disabled = !catalogue || pending.size > 0;
  }
}

for (const id of controls) {
  $(id).addEventListener(id === "search" ? "input" : "change", () => {
    page = 1;
    render();
    syncDetail();
  });
}
for (const suffix of ["", "-top"]) {
  $("previous" + suffix).addEventListener("click", () => { page--; render(); $("result-info").scrollIntoView({ block: "start" }); });
  $("next" + suffix).addEventListener("click", () => { page++; render(); $("result-info").scrollIntoView({ block: "start" }); });
}
$("reset").addEventListener("click", () => {
  for (const id of ["search", "group", "status", "category"]) $(id).value = "";
  $("only-selected").checked = false;
  page = 1;
  render();
});
$("retry").addEventListener("click", initialise);
$("close-detail").addEventListener("click", () => $("detail").close());
$("detail").addEventListener("close", () => { detailItem = null; noteDirty = false; });
$("detail-check").addEventListener("change", () => {
  if (detailItem) saveReview(detailItem, $("detail-check").checked);
});
$("detail-note").addEventListener("input", () => { noteDirty = true; $("note-status").textContent = "原因尚未保存"; });
$("save-note").addEventListener("click", () => {
  if (detailItem) saveReview(detailItem, true, $("detail-note").value);
});
$("export").addEventListener("click", async () => {
  try {
    const result = await api("/api/rework");
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "tag-icons-rework.json";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(`已导出 ${result.rework_count} 项重做标记`);
  } catch (error) { toast(error.message || "导出失败，请重试。"); }
});
window.addEventListener("beforeunload", (event) => {
  if (!pending.size) return;
  event.preventDefault();
  event.returnValue = "";
});
setInterval(() => {
  if (!loading && catalogue && !pending.size && document.visibilityState === "visible") {
    refreshState().catch(() => savedStatus("本机后台连接中断，请刷新", "failed"));
  }
}, 8000);
initialise();
