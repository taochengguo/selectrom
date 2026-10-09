"""Tianditu location lookups for on-site sampling reports."""

import json
import logging
import math
import re
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

from django.conf import settings

from sampling.services.tianditu_direct import DirectNetworkError, get_json as direct_get_json


class TiandituServiceError(ValueError):
    pass


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReverseGeocodeResult:
    address: str
    city: str


def canonical_city(value):
    text = re.sub(r"\s+", "", value or "")
    for municipality in ("北京市", "天津市", "上海市", "重庆市"):
        if municipality in text:
            return municipality
    text = re.split(r"省|自治区", text, maxsplit=1)[-1]
    match = re.search(r"([\u4e00-\u9fff]+?(?:自治州|地区|盟|市))", text)
    return match.group(1) if match else ""


def _request_json(url, purpose):
    try:
        if settings.TIANDITU_DIRECT_EGRESS:
            return _direct_request_json(url)
        with urlopen(url, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        headers = error.headers or {}
        event_id = headers.get("Block-Event-Id", "")
        detail = ""
        if error.code in {401, 403} and not event_id:
            try:
                body = json.loads(error.read(4096).decode("utf-8"))
                if isinstance(body, dict):
                    message = body.get("msg") or body.get("message") or body.get("info")
                    resolution = body.get("resolve")
                    parts = [part for part in (message, resolution) if isinstance(part, str) and part.strip()]
                    detail = "；".join(parts).replace(settings.TIANDITU_API_KEY, "***").strip()[:180]
            except (OSError, UnicodeError, ValueError):
                pass
        logger.warning(
            "Tianditu %s API %s returned HTTP %s; block_event_id=%s",
            purpose,
            urlsplit(url).path,
            error.code,
            event_id,
        )
        if event_id and error.code in {403, 418}:
            raise TiandituServiceError(
                f"天地图{purpose}被安全策略拦截（HTTP {error.code}，事件ID：{event_id}）"
            ) from error
        if error.code == 418:
            raise TiandituServiceError(f"天地图{purpose}被安全策略拦截（HTTP 418）") from error
        if error.code in {401, 403}:
            explanation = detail or "请检查 Key 的接口权限与来源限制"
            raise TiandituServiceError(
                f"天地图{purpose}拒绝访问（HTTP {error.code}）：{explanation}"
            ) from error
        raise TiandituServiceError(f"天地图{purpose}请求失败（HTTP {error.code}）") from error
    except DirectNetworkError as error:
        logger.warning("Tianditu API %s direct connection failed: %s", urlsplit(url).path, error)
        raise TiandituServiceError(f"天地图实体网卡直连失败：{error}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        logger.warning("Tianditu API %s failed: %s", urlsplit(url).path, type(error).__name__)
        raise TiandituServiceError("天地图请求或响应解析失败") from error


def _direct_request_json(url):
    return direct_get_json(
        url,
        source_ip=settings.TIANDITU_DIRECT_SOURCE_IP,
        interface_index=settings.TIANDITU_DIRECT_INTERFACE_INDEX,
        dns_servers=settings.TIANDITU_DIRECT_DNS_SERVERS,
    )


def reverse_geocode(longitude, latitude):
    token = settings.TIANDITU_API_KEY
    if not token:
        raise TiandituServiceError("尚未配置天地图 API Key")
    query = {"lon": longitude, "lat": latitude, "ver": 1}
    url = "https://api.tianditu.gov.cn/geocoder?" + urlencode(
        {"postStr": json.dumps(query), "type": "geocode", "tk": token}
    )
    payload = _request_json(url, "现场地址解析")
    if not isinstance(payload, dict) or str(payload.get("status")) != "0":
        raise TiandituServiceError("天地图未能解析打卡位置")
    result = payload.get("result") or {}
    if not isinstance(result, dict):
        raise TiandituServiceError("天地图未返回打卡位置的地址")
    address = result.get("formatted_address")
    if not isinstance(address, str) or not address.strip():
        raise TiandituServiceError("天地图未返回打卡位置的地址")
    component = result.get("addressComponent") or {}
    city_text = component.get("city", "") if isinstance(component, dict) else ""
    city = canonical_city(city_text) or canonical_city(address)
    if not city:
        raise TiandituServiceError("天地图未返回可识别的地市信息")
    return ReverseGeocodeResult(address=address.strip(), city=city)


def geocode_address(address):
    token = settings.TIANDITU_API_KEY
    if not token:
        raise TiandituServiceError("尚未配置天地图 API Key")

    url = "https://api.tianditu.gov.cn/geocoder?" + urlencode(
        {"ds": json.dumps({"keyWord": address}, ensure_ascii=False), "tk": token}
    )
    payload = _request_json(url, "收货地址解析")
    if not isinstance(payload, dict) or str(payload.get("status")) != "0":
        raise TiandituServiceError("天地图未能解析收货地址")
    location = payload.get("location") or {}
    if not isinstance(location, dict) or "lon" not in location or "lat" not in location:
        raise TiandituServiceError("天地图未能定位任务的收货地址")
    try:
        longitude, latitude = float(location["lon"]), float(location["lat"])
    except (TypeError, ValueError) as error:
        raise TiandituServiceError("天地图返回的收货地址坐标无效") from error
    if not (
        math.isfinite(longitude)
        and math.isfinite(latitude)
        and -180 <= longitude <= 180
        and -90 <= latitude <= 90
    ):
        raise TiandituServiceError("天地图返回的收货地址坐标无效")
    return longitude, latitude
