function appendTextElement(parent, tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  parent.append(element);
  return element;
}

async function postForm(url, csrfToken, values) {
  const body = new URLSearchParams(values);
  const response = await fetch(url, {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken, Accept: "application/json" },
    body,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "保存失败，请稍后重试");
  return payload;
}

function renderCheckin(history, item) {
  const row = document.createElement("li");
  appendTextElement(row, "strong", item.status_label);
  appendTextElement(row, "span", `${new Date(item.created_at).toLocaleString("zh-CN")} · ${item.actor}`);
  if (item.location_city) appendTextElement(row, "span", `现场地市：${item.location_city}`);
  if (item.location_address) {
    appendTextElement(row, "span", `现场地址：${item.location_address}`);
  }
  if (item.note) appendTextElement(row, "p", `备注：${item.note}`);
  history.prepend(row);
}

function addPhotoPreviews(report) {
  const preview = report.querySelector("[data-report-photo-preview]");
  const empty = report.querySelector("[data-photo-empty]");
  const gallery = report.querySelector("[data-photo-gallery]");
  const count = report.querySelector("[data-photo-count]");
  const add = report.querySelector("[data-photo-add]");
  const status = report.querySelector("[data-photo-status]");
  const camera = report.querySelector("[data-photo-camera-input]");
  const album = report.querySelector("[data-photo-album-input]");
  const csrfToken = report.querySelector("[name=csrfmiddlewaretoken]").value;
  const refresh = () => {
    const total = preview.querySelectorAll("[data-photo-id]").length;
    count.textContent = total;
    empty.hidden = total > 0;
    gallery.hidden = total === 0;
    add.hidden = total >= 3;
  };
  const selectAlbum = () => album.click();
  report.querySelector("[data-photo-camera]").addEventListener("click", () => camera.click());
  report.querySelector("[data-photo-album]").addEventListener("click", selectAlbum);
  add.addEventListener("click", selectAlbum);
  for (const input of [camera, album]) input.addEventListener("change", async () => {
    const files = [...input.files];
    const remaining = 3 - preview.querySelectorAll("[data-photo-id]").length;
    input.value = "";
    if (files.length > remaining) { status.textContent = `最多上传 3 张照片，还可添加 ${remaining} 张`; return; }
    for (const file of files) {
      status.textContent = "正在上传照片…";
      const body = new FormData();
      body.append("photo", file);
      try {
        const response = await fetch(report.dataset.photosUrl, { method: "POST", headers: { "X-CSRFToken": csrfToken, Accept: "application/json" }, body });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "上传失败");
        const tile = document.createElement("div");
        tile.className = "report-photo-tile";
        tile.dataset.photoId = result.photo.id;
        tile.dataset.photoUrl = result.photo.url;
        const image = document.createElement("img");
        image.src = result.photo.url;
        image.alt = result.photo.name;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.dataset.photoDelete = "";
        remove.dataset.deleteUrl = result.photo.delete_url;
        remove.setAttribute("aria-label", "删除照片");
        remove.textContent = "×";
        tile.append(image, remove);
        preview.insertBefore(tile, add);
        refresh();
        status.textContent = "照片已保存";
      } catch (error) { status.textContent = error.message; break; }
    }
  });
  preview.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-photo-delete]");
    if (!button) return;
    button.disabled = true;
    try {
      const response = await fetch(button.dataset.deleteUrl, { method: "POST", headers: { "X-CSRFToken": csrfToken, Accept: "application/json" } });
      if (!response.ok) throw new Error("删除失败，请重试");
      button.closest("[data-photo-id]").remove();
      refresh();
      status.textContent = "照片已删除";
    } catch (error) { button.disabled = false; status.textContent = error.message; }
  });
  refresh();
}

function exportReport(report) {
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    window.alert("浏览器拦截了报告窗口，请允许此页面打开弹窗后重试。");
    return;
  }
  const doc = printWindow.document;
  doc.title = `抽检报告-${report.dataset.exportTitle}`;
  const style = doc.createElement("style");
  style.textContent = `
    body { margin: 0; color: #17243a; font: 15px/1.65 Arial, sans-serif; }
    main { max-width: 900px; margin: 32px auto; padding: 0 28px; }
    h1 { margin-bottom: 6px; font-size: 26px; } h2 { margin-top: 28px; font-size: 19px; }
    dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 20px; }
    dl div { display: grid; grid-template-columns: 120px 1fr; }
    dt { color: #58677e; } dd { margin: 0; overflow-wrap: anywhere; }
    img { max-width: 100%; max-height: 680px; object-fit: contain; margin: 8px; }
    .photos { display: flex; flex-wrap: wrap; gap: 10px; }
    @media print { main { margin: 0 auto; padding: 0; } }
  `;
  doc.head.append(style);
  const main = doc.createElement("main");
  appendTextElement(main, "h1", "抽检报告");
  appendTextElement(main, "p", report.dataset.exportTitle);

  const taskDetails = document.querySelector(".detail-list");
  if (taskDetails) {
    appendTextElement(main, "h2", "任务信息");
    main.append(taskDetails.cloneNode(true));
  }
  appendTextElement(main, "h2", "抽样检测结果");
  main.append(report.querySelector("[data-report-samples]").cloneNode(true));
  appendTextElement(main, "p", report.querySelector("textarea[name=inspection_result]").value.trim() || "未填写检测结果");
  appendTextElement(main, "h2", "现场打卡记录");
  const checkins = report.querySelector("[data-checkin-history]");
  if (checkins.children.length) main.append(checkins.cloneNode(true));
  else appendTextElement(main, "p", "暂无打卡记录");

  const photos = report.querySelectorAll("[data-photo-id]");
  if (photos.length) {
    appendTextElement(main, "h2", "现场抽检照片");
    const photoList = document.createElement("div");
    photoList.className = "photos";
    for (const photo of photos) {
      const image = doc.createElement("img");
      image.src = photo.dataset.photoUrl;
      image.alt = photo.querySelector("img").alt;
      photoList.append(image);
    }
    main.append(photoList);
  }
  doc.body.append(main);
  const imageLoads = [...main.querySelectorAll("img")].map((image) => image.decode().catch(() => {}));
  Promise.race([
    Promise.all(imageLoads),
    new Promise((resolve) => window.setTimeout(resolve, 3000)),
  ]).then(() => printWindow.print());
}

for (const report of document.querySelectorAll("[data-sampling-report]")) {
  const form = report.querySelector("[data-report-form]");
  const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
  const saveStatus = report.querySelector("[data-report-save-status]");
  const checkinError = report.querySelector("[data-checkin-error]");
  const history = report.querySelector("[data-checkin-history]");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    saveStatus.textContent = "正在保存…";
    try {
      await postForm(form.action, csrfToken, {
        inspection_result: form.elements.namedItem("inspection_result").value,
      });
      saveStatus.textContent = "检测结果已保存";
    } catch (error) {
      saveStatus.textContent = error.message;
    }
  });

  report.querySelector("[data-site-checkin]").addEventListener("click", () => {
    checkinError.textContent = "正在获取当前位置…";
    const submit = async (latitude, longitude, note = "") => {
      try {
        const result = await postForm(report.dataset.checkinUrl, csrfToken, {
          latitude: latitude ?? "", longitude: longitude ?? "", note,
        });
        if (result.requires_note) {
          const exceptionNote = window.prompt(`${result.message}\n请填写异常打卡备注：`);
          if (!exceptionNote?.trim()) {
            checkinError.textContent = "未填写备注，异常打卡未保存";
            return;
          }
          await submit(latitude, longitude, exceptionNote.trim());
          return;
        }
        renderCheckin(history, result);
        checkinError.textContent = `${result.status_label}，记录已保存`;
      } catch (error) {
        checkinError.textContent = error.message;
      }
    };

    // Mobile browsers only expose geolocation to secure contexts. LAN preview
    // links are HTTP, so explain the actual blocker instead of silently
    // falling through to an abnormal check-in with no coordinates.
    if (window.isSecureContext === false) {
      checkinError.textContent = "当前页面不是安全连接，手机浏览器不会开放定位权限。请使用 HTTPS 地址重新打开页面后再打卡。";
      return;
    }
    if (!navigator.geolocation) {
      checkinError.textContent = "当前浏览器不支持设备定位，请使用支持定位的手机浏览器，并通过 HTTPS 打开页面。";
      submit(null, null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => submit(coords.latitude, coords.longitude),
      (error) => {
        const messages = {
          1: "定位权限被拒绝。请在手机浏览器的网站权限设置中允许本网站使用位置信息，然后重试。",
          2: "暂时无法确定当前位置，请检查手机的定位服务是否已开启后重试。",
          3: "获取位置超时，请确认手机定位服务已开启并重试。",
        };
        checkinError.textContent = messages[error.code] || "获取位置失败，请检查手机定位服务和浏览器权限后重试。";
        submit(null, null);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });

  report.querySelector("[data-export-report]").addEventListener("click", () => exportReport(report));
  addPhotoPreviews(report);
}
