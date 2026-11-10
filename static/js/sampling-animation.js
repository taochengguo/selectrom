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
  const progress = reel.querySelector('.sampling-progress');
  const chamber = reel.querySelector('.sampling-chamber');
  const output = reel.querySelector('.sampling-picked');
  output.replaceChildren();
  const size = chamber.clientWidth;
  const diameter = 38;
  const radius = (size - diameter) / 2 - 6;
  const center = size / 2;
  const poolSize = Number(formData.get('sample_quantity')) || Math.max(18, labels.length);
  const balls = Array.from({length: Math.min(18, poolSize)}, (_, index) => {
    const element = document.createElement('span');
    element.className = 'sampling-ball';
    element.textContent = String(index + 1).padStart(2, '0');
    chamber.append(element);
    const angle = Math.random() * Math.PI * 2;
    const distance = Math.sqrt(Math.random()) * radius;
    return {element, x: center + Math.cos(angle) * distance - diameter / 2,
      y: center + Math.sin(angle) * distance - diameter / 2,
      vx: (Math.random() - .5) * 4, vy: (Math.random() - .5) * 4};
  });
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let frame;
  const animate = () => {
    for (const ball of balls) {
      ball.x += ball.vx; ball.y += ball.vy;
      const dx = ball.x + diameter / 2 - center;
      const dy = ball.y + diameter / 2 - center;
      const distance = Math.hypot(dx, dy);
      if (distance > radius) {
        const nx = dx / distance, ny = dy / distance;
        const dot = ball.vx * nx + ball.vy * ny;
        ball.vx -= 2 * dot * nx; ball.vy -= 2 * dot * ny;
        ball.x = center + nx * radius - diameter / 2;
        ball.y = center + ny * radius - diameter / 2;
      }
      ball.element.style.transform = `translate(${ball.x}px, ${ball.y}px)`;
    }
    frame = requestAnimationFrame(animate);
  };
  if (!reducedMotion) animate();
  progress.textContent = `抽样进度：0 / ${labels.length}`;
  try {
    await new Promise(resolve => setTimeout(resolve, reducedMotion ? 0 : 3000));
    for (const [index, label] of labels.entries()) {
      const ball = document.createElement('span');
      ball.className = 'sampling-ball sampling-ball--picked';
      ball.textContent = label;
      output.append(ball);
      progress.textContent = `抽样进度：${index + 1} / ${labels.length}`;
      await new Promise(resolve => setTimeout(resolve, reducedMotion ? 0 : 1200));
    }
    await new Promise(resolve => setTimeout(resolve, reducedMotion ? 0 : 1000));
  } finally { if (frame) cancelAnimationFrame(frame); }
  resultList.replaceChildren(...payload.results.map(renderResultCard));
  return payload;
}
