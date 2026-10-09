function appendField(list, label, value) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = String(value);
  row.append(term, description);
  list.append(row);
}

export function renderResultCard(item) {
  const card = document.createElement("article");
  const heading = document.createElement("h3");
  const fields = document.createElement("dl");
  if (item.sample_number != null) {
    heading.textContent = `第 ${item.sample_number} 件样品`;
    card.append(heading);
    return card;
  }
  heading.textContent = item.material_number;
  appendField(fields, "订单号", item.order_number);
  appendField(fields, "供应商", item.supplier);
  appendField(fields, "物资名称", item.material_name);
  appendField(fields, "物资数量", item.quantity);
  appendField(fields, "抽样数量", item.sampling_quantity);
  card.append(heading, fields);
  return card;
}

export async function runSamplingAnimation({
  trigger,
  reel,
  resultList,
  endpoint,
  csrfToken,
  formData,
}) {
  trigger.disabled = true;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken, Accept: "application/json" },
    body: formData,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "抽样失败");
  }

  const labels = payload.results.map((item) => item.sample_number != null ? `第 ${item.sample_number} 件` : item.material_number);
  if (labels.length === 0) {
    throw new Error("抽样结果为空");
  }
  let tick = 0;
  const timer = window.setInterval(() => {
    reel.textContent = labels[tick % labels.length];
    tick += 1;
  }, 70);
  await new Promise((resolve) => window.setTimeout(resolve, 1400));
  window.clearInterval(timer);
  reel.textContent = labels[labels.length - 1];
  resultList.replaceChildren(...payload.results.map(renderResultCard));
  return payload;
}
