from io import BytesIO
import re
from xml.sax.saxutils import escape

from django.utils import timezone
from PIL import Image as PillowImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image


def report_filename(task):
    latest = task.sampling_batches.filter(status="locked", drawn_at__isnull=False).order_by("-drawn_at", "-version").first()
    if latest is None:
        raise ValueError("任务缺少实际抽样日期，无法导出报告")
    date = timezone.localtime(latest.drawn_at).strftime("%Y%m%d")
    def safe(value):
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:80] or "未填写"
    return f"{date}_{safe(task.purchase_order_number)}_{safe(task.task_number)}.pdf"


def build_report_pdf(task, batches, storage):
    """Generate a paginated, read-only report from saved task data."""
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    body = ParagraphStyle("body", fontName="STSong-Light", fontSize=10, leading=16, wordWrap="CJK")
    heading = ParagraphStyle("heading", parent=body, fontSize=14, leading=22, spaceBefore=14, spaceAfter=8)
    title = ParagraphStyle("title", parent=heading, fontSize=20, alignment=TA_CENTER)

    def text(value, style=body):
        return Paragraph(escape(str(value if value is not None and value != "" else "无")).replace("\n", "<br/>"), style)

    content = [text("抽样报告", title), text("任务详情", heading)]
    fields = [("任务编号", task.task_number), ("任务名称", task.name), ("任务状态", task.get_status_display())]
    if task.sample_mode == "unit":
        fields += [(label, getattr(task, key)) for label, key in [
            ("质检类型", "inspection_type"), ("抽样采购订单号", "purchase_order_number"),
            ("订单行项ID", "order_line_id"), ("收货单位", "receiving_unit"),
            ("供应商名称", "supplier_name"), ("物资编码", "material_code"),
            ("物资名称", "material_name"), ("规格型号", "specification"),
            ("联系人", "contact_name"), ("收货人电话", "receiver_phone"),
            ("收货地址", "delivery_address"), ("详细地址", "detailed_address"), ("样品数量", "sample_quantity"),
            ("抽样样品数", "draw_count"), ("计划抽检日期", "planned_inspection_date"),
        ]]
    else:
        fields += [("候选物资", task.candidates.count()), ("抽取数量", task.draw_count),
                   ("计划时间", timezone.localtime(task.planned_at).strftime("%Y-%m-%d %H:%M") if task.planned_at else "未设置")]
    fields.append(("任务备注", task.notes))
    table = Table([[text(label), text(value)] for label, value in fields], colWidths=[38 * mm, 136 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf4fc")),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#dce5f1")),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    content.append(table)
    for batch in batches:
        content.extend([text("抽样报告详情", heading), text(f"第 {batch.version} 次 · {batch.get_kind_display()} · {timezone.localtime(batch.drawn_at):%Y-%m-%d %H:%M}")])
        content.append(text("抽样检测样品", heading))
        for result in batch.results.select_related("material").order_by("sequence"):
            if result.sample_number is not None:
                content.append(text(f"第 {result.sample_number} 号样品"))
            else:
                material = result.material
                content.append(text(f"{material.material_number} · {material.material_name} · 订单号：{material.order_number} · 供应商：{material.supplier} · 物资数量：{material.quantity} · 抽样数量：{task.draw_count}"))
        report = getattr(batch, "report", None)
        content.extend([text("抽样检测结果", heading), text(report.inspection_result if report else "未填写检测结果")])
        content.append(text("现场打卡记录", heading))
        checkins = list(report.checkins.select_related("created_by").all()) if report else []
        if not checkins:
            content.append(text("暂无打卡记录"))
        for checkin in checkins:
            actor = checkin.created_by
            content.append(text(f"{checkin.get_status_display()} · {timezone.localtime(checkin.created_at):%Y-%m-%d %H:%M:%S} · {(actor.get_full_name() or actor.username) if actor else '无'}"))
            for label, value in [("现场地市", checkin.location_city), ("现场地址", checkin.location_address), ("备注", checkin.note)]:
                if value:
                    content.append(text(f"{label}：{value}"))
            if checkin.latitude is not None and checkin.longitude is not None:
                content.append(text(f"坐标：{checkin.longitude}, {checkin.latitude}"))
            content.append(Spacer(1, 6))
        content.append(text("编号样品照片", heading))
        photos = list(batch.photos.all())
        if not photos:
            content.append(text("暂无照片"))
        for photo in photos:
            if not storage.exists(photo.path):
                content.append(text(f"照片文件缺失：{photo.original_name}"))
                continue
            with storage.open(photo.path, "rb") as source, PillowImage.open(source) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
                image.thumbnail((1800, 1800))
                data = BytesIO()
                image.save(data, format="JPEG", quality=90)
                data.seek(0)
                scale = min(174 * mm / image.width, 180 * mm / image.height)
                content.extend([text(photo.original_name), Image(data, width=image.width * scale, height=image.height * scale), Spacer(1, 10)])

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=(210 * mm, 297 * mm), rightMargin=18 * mm,
                                 leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                                 title=f"抽样报告-{task.task_number}", author="随机抽样系统")

    def footer(canvas, doc):
        canvas.setFont("STSong-Light", 9)
        canvas.drawCentredString(105 * mm, 10 * mm, f"第 {doc.page} 页")

    document.build(content, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output

