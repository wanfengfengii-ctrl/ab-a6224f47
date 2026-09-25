"use strict";

const MIN_DAMAGES = 3;
const MAX_DAMAGES = 5;
const MIN_SCRAPS = 4;
const MAX_SCRAPS = 8;
const DRAFT_KEY = "guji-patch-draft-v1";

const EXAMPLE = {
  damages: [
    { id: "D1", width: 8, height: 10, phaseMin: 0, phaseMax: 5 },
    { id: "D2", width: 8, height: 10, phaseMin: 0, phaseMax: 5 },
    { id: "D3", width: 8, height: 10, phaseMin: 0, phaseMax: 5 },
  ],
  scraps: [
    { id: "S1", x: 0, y: 0, width: 40, height: 20, period: 6, origin: 0, maxUses: 3 },
    { id: "S2", x: 0, y: 0, width: 30, height: 20, period: 6, origin: 0, maxUses: 1 },
    { id: "S3", x: 5, y: 0, width: 30, height: 20, period: 6, origin: 2, maxUses: 1 },
    { id: "S4", x: 0, y: 0, width: 25, height: 12, period: 6, origin: 0, maxUses: 1 },
  ],
};

const CONSTRAINT_LABELS = {
  piece_exceeds_region: "裁片超出可裁区域",
  phase_range_unreachable: "水印相位范围不可达",
  phase_continuity: "相邻破损相位不连续",
  scrap_capacity_or_overlap: "边料可用次数 / 重叠冲突",
};

let damages = [];
let scraps = [];

function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

function nextId(prefix, rows) {
  const used = new Set(rows.map((r) => String(r.id)));
  let n = rows.length + 1;
  while (used.has(prefix + n)) n += 1;
  return prefix + n;
}

function el(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function inputCell(row, key, numeric) {
  const td = el("td");
  const input = el("input");
  if (numeric) {
    input.type = "number";
    input.min = "0";
    input.step = "1";
  } else {
    input.type = "text";
    input.maxLength = 40;
  }
  input.value = row[key];
  input.addEventListener("input", () => {
    row[key] = input.value;
  });
  td.append(input);
  return td;
}

function renderTables() {
  const dtb = document.querySelector("#damageTable tbody");
  dtb.innerHTML = "";
  damages.forEach((d, i) => {
    const tr = el("tr");
    tr.append(el("td", String(i + 1)));
    ["id", "width", "height", "phaseMin", "phaseMax"].forEach((k) =>
      tr.append(inputCell(d, k, k !== "id"))
    );
    const td = el("td");
    const del = el("button", "删除");
    del.disabled = damages.length <= MIN_DAMAGES;
    del.addEventListener("click", () => {
      damages.splice(i, 1);
      renderTables();
    });
    td.append(del);
    tr.append(td);
    dtb.append(tr);
  });

  const stb = document.querySelector("#scrapTable tbody");
  stb.innerHTML = "";
  scraps.forEach((s, i) => {
    const tr = el("tr");
    ["id", "x", "y", "width", "height", "period", "origin", "maxUses"].forEach((k) =>
      tr.append(inputCell(s, k, k !== "id"))
    );
    const td = el("td");
    const del = el("button", "删除");
    del.disabled = scraps.length <= MIN_SCRAPS;
    del.addEventListener("click", () => {
      scraps.splice(i, 1);
      renderTables();
    });
    td.append(del);
    tr.append(td);
    stb.append(tr);
  });

  document.querySelector("#addDamage").disabled = damages.length >= MAX_DAMAGES;
  document.querySelector("#addScrap").disabled = scraps.length >= MAX_SCRAPS;
}

function toInt(v) {
  if (typeof v === "number" && Number.isInteger(v)) return v;
  const t = String(v).trim();
  if (t === "" || !/^-?\d+$/.test(t)) return NaN;
  return parseInt(t, 10);
}

function collectPayload() {
  const errs = [];
  const ds = [];
  const dIds = new Set();
  damages.forEach((d, i) => {
    const where = `破损第 ${i + 1} 行`;
    const row = {
      id: String(d.id).trim(),
      width: toInt(d.width),
      height: toInt(d.height),
      phaseMin: toInt(d.phaseMin),
      phaseMax: toInt(d.phaseMax),
    };
    if (!row.id) errs.push(`${where}：名称不能为空`);
    else if (dIds.has(row.id)) errs.push(`${where}：名称「${row.id}」重复`);
    dIds.add(row.id);
    for (const [k, label] of [["width", "宽"], ["height", "高"]]) {
      if (!Number.isInteger(row[k]) || row[k] < 1)
        errs.push(`${where}：${label}必须为不小于 1 的整数`);
    }
    for (const [k, label] of [["phaseMin", "相位下限"], ["phaseMax", "相位上限"]]) {
      if (!Number.isInteger(row[k]) || row[k] < 0)
        errs.push(`${where}：${label}必须为非负整数`);
    }
    if (
      Number.isInteger(row.phaseMin) &&
      Number.isInteger(row.phaseMax) &&
      row.phaseMax < row.phaseMin
    )
      errs.push(`${where}：相位上限不能小于下限`);
    ds.push(row);
  });

  const ss = [];
  const sIds = new Set();
  scraps.forEach((s, i) => {
    const where = `边料第 ${i + 1} 行`;
    const row = {
      id: String(s.id).trim(),
      region: {
        x: toInt(s.x),
        y: toInt(s.y),
        width: toInt(s.width),
        height: toInt(s.height),
      },
      period: toInt(s.period),
      origin: toInt(s.origin),
      maxUses: toInt(s.maxUses),
    };
    if (!row.id) errs.push(`${where}：名称不能为空`);
    else if (sIds.has(row.id)) errs.push(`${where}：名称「${row.id}」重复`);
    sIds.add(row.id);
    for (const [v, label] of [
      [row.region.x, "区域 X"],
      [row.region.y, "区域 Y"],
      [row.origin, "相位原点"],
    ]) {
      if (!Number.isInteger(v) || v < 0) errs.push(`${where}：${label}必须为非负整数`);
    }
    for (const [v, label] of [
      [row.region.width, "区域宽"],
      [row.region.height, "区域高"],
      [row.period, "纹样周期"],
      [row.maxUses, "可用次数"],
    ]) {
      if (!Number.isInteger(v) || v < 1)
        errs.push(`${where}：${label}必须为不小于 1 的整数`);
    }
    ss.push(row);
  });

  if (ds.length < MIN_DAMAGES || ds.length > MAX_DAMAGES)
    errs.push(`破损数量须在 ${MIN_DAMAGES}–${MAX_DAMAGES} 之间`);
  if (ss.length < MIN_SCRAPS || ss.length > MAX_SCRAPS)
    errs.push(`边料数量须在 ${MIN_SCRAPS}–${MAX_SCRAPS} 之间`);
  if (errs.length) {
    const e = new Error(errs.join("；"));
    e.validation = true;
    throw e;
  }
  return { damages: ds, scraps: ss };
}

function rawDetails(data) {
  const det = el("details");
  const sum = el("summary", "查看原始响应");
  const pre = el("pre", JSON.stringify(data, null, 2));
  det.append(sum);
  det.append(pre);
  return det;
}

function renderError(title, message) {
  const box = el("div", "");
  box.className = "result-error";
  box.append(el("h2", title));
  box.append(el("p", message));
  return box;
}

function renderFeasible(data) {
  const box = el("div");
  box.className = "result-ok";
  box.append(el("h2", "配片成功"));
  const o = data.objectives;
  box.append(
    el(
      "p",
      `使用边料 ${o.scrapsUsed} 张 · 裁切废料总面积 ${o.wasteArea}` +
        `（被用区域 ${o.usedRegionArea} − 裁片 ${o.piecesArea}）`
    )
  );
  const table = el("table");
  table.className = "grid";
  const head = el("tr");
  ["破损", "边料", "裁切起点", "宽×高", "左缘相位", "右缘相位"].forEach((t) =>
    head.append(el("th", t))
  );
  const thead = el("thead");
  thead.append(head);
  table.append(thead);
  const tb = el("tbody");
  data.plan.forEach((p) => {
    const tr = el("tr");
    [p.damageId, p.scrapId, p.start, `${p.width}×${p.height}`, p.leftPhase, p.rightPhase]
      .forEach((v) => tr.append(el("td", String(v))));
    tb.append(tr);
  });
  table.append(tb);
  box.append(table);
  box.append(rawDetails(data));
  return box;
}

function renderInfeasible(data) {
  const box = el("div");
  box.className = "result-warn";
  box.append(el("h2", "无法配片"));
  const ev = data.evidence || {};
  const label = CONSTRAINT_LABELS[ev.constraint] || ev.constraint || "未知约束";
  box.append(el("p", `首条约束证据：${label}（第 ${(ev.damageIndex ?? 0) + 1} 处破损）`));
  box.append(el("p", ev.message || ""));
  box.append(rawDetails(data));
  return box;
}

function formatDetail(data) {
  if (!data) return "无响应内容";
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((d) => `${(d.loc || []).join(".")}: ${d.msg}`)
      .join("；");
  }
  if (typeof data.detail === "string") return data.detail;
  return JSON.stringify(data);
}

function showResult(node) {
  const r = document.querySelector("#result");
  r.classList.remove("hidden");
  r.innerHTML = "";
  r.append(node);
  r.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function solve() {
  let payload;
  try {
    payload = collectPayload();
  } catch (e) {
    showResult(renderError("输入校验未通过", e.message));
    return;
  }
  const btn = document.querySelector("#solveBtn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => null);
    if (res.status === 422) {
      showResult(renderError("请求校验失败", formatDetail(data)));
    } else if (!res.ok) {
      showResult(renderError(`服务返回 ${res.status}`, formatDetail(data)));
    } else if (data && data.status === "feasible") {
      showResult(renderFeasible(data));
    } else {
      showResult(renderInfeasible(data));
    }
  } catch (e) {
    showResult(renderError("无法连接服务", String(e)));
  } finally {
    btn.disabled = false;
  }
}

let toastTimer = null;
function toast(msg) {
  const t = document.querySelector("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 2000);
}

function saveDraft() {
  localStorage.setItem(DRAFT_KEY, JSON.stringify({ damages, scraps }));
  toast("草稿已保存");
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return false;
    const d = JSON.parse(raw);
    if (!Array.isArray(d.damages) || !Array.isArray(d.scraps)) return false;
    damages = d.damages;
    scraps = d.scraps;
    return true;
  } catch (e) {
    return false;
  }
}

function init() {
  if (!loadDraft()) {
    damages = clone(EXAMPLE.damages);
    scraps = clone(EXAMPLE.scraps);
  }
  renderTables();
  document.querySelector("#addDamage").addEventListener("click", () => {
    if (damages.length >= MAX_DAMAGES) return;
    damages.push({ id: nextId("D", damages), width: 8, height: 10, phaseMin: 0, phaseMax: 5 });
    renderTables();
  });
  document.querySelector("#addScrap").addEventListener("click", () => {
    if (scraps.length >= MAX_SCRAPS) return;
    scraps.push({ id: nextId("S", scraps), x: 0, y: 0, width: 30, height: 20, period: 6, origin: 0, maxUses: 1 });
    renderTables();
  });
  document.querySelector("#loadExample").addEventListener("click", () => {
    damages = clone(EXAMPLE.damages);
    scraps = clone(EXAMPLE.scraps);
    renderTables();
    toast("已载入示例");
  });
  document.querySelector("#saveDraft").addEventListener("click", saveDraft);
  document.querySelector("#clearDraft").addEventListener("click", () => {
    localStorage.removeItem(DRAFT_KEY);
    toast("草稿已清除");
  });
  document.querySelector("#solveBtn").addEventListener("click", solve);
}

document.addEventListener("DOMContentLoaded", init);
