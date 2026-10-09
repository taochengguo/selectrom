import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import PersonnelAssignment, SamplingBatch, SamplingCheckIn, SamplingTask
from sampling.services.reports import record_checkin
from sampling.services.tianditu import (
    ReverseGeocodeResult, TiandituServiceError, canonical_city,
    geocode_address, reverse_geocode,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@override_settings(TIANDITU_DIRECT_EGRESS=False)
class TiandituGeocodingTests(SimpleTestCase):
    @override_settings(TIANDITU_API_KEY="test-key")
    @patch("sampling.services.tianditu.urlopen")
    def test_geocodes_address_and_reads_location(self, urlopen):
        urlopen.return_value = _Response({
            "status": "0",
            "location": {"lon": 116.397, "lat": 39.908, "level": "道路"},
        })
        self.assertEqual(geocode_address("北京市东城区测试路1号"), (116.397, 39.908))
        url = urlparse(urlopen.call_args.args[0])
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.path, "/geocoder")
        params = parse_qs(url.query)
        self.assertEqual(params["tk"], ["test-key"])
        self.assertEqual(json.loads(params["ds"][0])["keyWord"], "北京市东城区测试路1号")

    @override_settings(TIANDITU_API_KEY="test-key")
    @patch("sampling.services.tianditu.urlopen")
    def test_city_level_address_can_be_geocoded(self, urlopen):
        urlopen.return_value = _Response({
            "status": "0",
            "location": {"lon": 116.4, "lat": 39.9, "level": "城市"},
        })
        self.assertEqual(geocode_address("六安"), (116.4, 39.9))

    def test_city_names_are_normalized_across_districts(self):
        self.assertEqual(canonical_city("北京市西城区"), "北京市")
        self.assertEqual(canonical_city("安徽省六安市金安区"), "六安市")
        self.assertEqual(canonical_city("安徽省六安市裕安区"), "六安市")

    @override_settings(TIANDITU_API_KEY="")
    def test_missing_key_is_reported(self):
        with self.assertRaisesMessage(TiandituServiceError, "API Key"):
            geocode_address("北京市东城区测试路1号")

    @override_settings(TIANDITU_API_KEY="test-key")
    @patch("sampling.services.tianditu.urlopen")
    def test_cloud_waf_rejection_is_reported(self, urlopen):
        urlopen.side_effect = HTTPError("https://api.tianditu.gov.cn/geocoder", 418, "", {}, None)
        with self.assertRaisesMessage(TiandituServiceError, "HTTP 418"):
            geocode_address("北京市东城区测试路1号")

    @override_settings(TIANDITU_API_KEY="test-key", TIANDITU_DIRECT_EGRESS=True)
    @patch("sampling.services.tianditu._direct_request_json", create=True)
    @patch("sampling.services.tianditu.urlopen")
    def test_direct_egress_avoids_proxy_block(self, urlopen, direct_request):
        urlopen.side_effect = HTTPError("https://api.tianditu.gov.cn/geocoder", 418, "", {}, None)
        direct_request.return_value = {
            "status": "0",
            "result": {
                "formatted_address": "北京市东城区测试路1号",
                "addressComponent": {"city": "北京市"},
            },
        }

        self.assertEqual(
            reverse_geocode(116.397, 39.908),
            ReverseGeocodeResult("北京市东城区测试路1号", "北京市"),
        )

    @override_settings(TIANDITU_API_KEY="test-key")
    @patch("sampling.services.tianditu.urlopen")
    def test_permission_denial_identifies_key_configuration(self, urlopen):
        urlopen.side_effect = HTTPError("https://api.tianditu.gov.cn/geocoder", 403, "", {}, None)
        with self.assertRaisesMessage(TiandituServiceError, "Key 的接口权限与来源限制"):
            reverse_geocode(116.37304, 39.92594)

    @override_settings(TIANDITU_API_KEY="test-key")
    @patch("sampling.services.tianditu.urlopen")
    def test_permission_denial_preserves_safe_api_message(self, urlopen):
        urlopen.side_effect = HTTPError(
            "https://api.tianditu.gov.cn/geocoder", 403, "", {},
            BytesIO(b'{"msg":"key test-key lacks geocoder permission","resolve":"use a server key"}'),
        )
        with self.assertRaisesMessage(TiandituServiceError, "key *** lacks geocoder permission；use a server key"):
            reverse_geocode(116.37304, 39.92594)

    @override_settings(TIANDITU_API_KEY="test-key")
    @patch("sampling.services.tianditu.urlopen")
    def test_waf_denial_includes_event_id(self, urlopen):
        urlopen.side_effect = HTTPError(
            "https://api.tianditu.gov.cn/geocoder", 403, "",
            {"Block-Event-Id": "test-event"}, None,
        )
        with self.assertRaisesMessage(TiandituServiceError, "test-event"):
            reverse_geocode(116.37304, 39.92594)

    @override_settings(TIANDITU_API_KEY="test-key")
    @patch("sampling.services.tianditu.urlopen")
    def test_reverse_geocodes_checkin_coordinates(self, urlopen):
        urlopen.return_value = _Response({
            "status": "0", "msg": "ok",
            "result": {
                "formatted_address": "北京市西城区西什库大街31号院23",
                "addressComponent": {"city": "北京市西城区"},
            },
        })
        self.assertEqual(
            reverse_geocode(116.37304, 39.92594),
            ReverseGeocodeResult("北京市西城区西什库大街31号院23", "北京市"),
        )
        url = urlparse(urlopen.call_args.args[0])
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.path, "/geocoder")
        params = parse_qs(url.query)
        self.assertEqual(params["type"], ["geocode"])
        self.assertEqual(params["tk"], ["test-key"])
        self.assertEqual(json.loads(params["postStr"][0]), {
            "lon": 116.37304, "lat": 39.92594, "ver": 1,
        })

class TiandituCheckinTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("map_admin", role=User.Role.ADMIN)
        self.sampler = User.objects.create_user("map_sampler", role=User.Role.SAMPLER)
        group = PersonnelGroup.objects.create(name="打卡组", created_by=self.admin)
        self.task = SamplingTask.objects.create(
            task_number="MAP-1", name="现场抽检", personnel_group=group,
            delivery_address="北京市东城区测试路1号", created_by=self.admin,
        )
        PersonnelAssignment.objects.create(
            task=self.task, candidate_user_ids=[self.sampler.pk],
            selected_user=self.sampler, kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True, created_by=self.admin,
        )
        self.batch = SamplingBatch.objects.create(
            task=self.task, version=1, kind=SamplingBatch.Kind.INITIAL,
            status=SamplingBatch.Status.LOCKED,
        )

    @patch("sampling.services.reports.reverse_geocode")
    @patch("sampling.services.reports.geocode_address", return_value=(116.397, 39.908))
    def test_same_city_and_cross_city_checkin(self, geocode, reverse_geocode_mock):
        def location(longitude, latitude):
            if longitude > 120:
                return ReverseGeocodeResult("上海市徐汇区测试路1号", "上海市")
            return ReverseGeocodeResult("北京市西城区测试路1号", "北京市")
        reverse_geocode_mock.side_effect = location
        near = record_checkin(
            task_id=self.task.pk, batch_id=self.batch.pk, actor=self.sampler,
            latitude=39.908, longitude=116.397,
        )
        self.assertEqual(near["status"], SamplingCheckIn.Status.SAME_CITY)
        self.assertEqual(near["location_address"], "北京市西城区测试路1号")
        self.assertEqual(near["location_city"], "北京市")

        same_city_far_away = record_checkin(
            task_id=self.task.pk, batch_id=self.batch.pk, actor=self.sampler,
            latitude=39.918, longitude=116.397,
        )
        self.assertEqual(same_city_far_away["status"], SamplingCheckIn.Status.SAME_CITY)
        far = record_checkin(
            task_id=self.task.pk, batch_id=self.batch.pk, actor=self.sampler,
            latitude=31.23, longitude=121.47,
        )
        self.assertTrue(far["requires_note"])
        self.assertEqual(far["status"], SamplingCheckIn.Status.OUTSIDE_CITY)
        self.assertEqual(SamplingCheckIn.objects.count(), 2)
        saved = record_checkin(
            task_id=self.task.pk, batch_id=self.batch.pk, actor=self.sampler,
            latitude=31.23, longitude=121.47, note="现场地址需要复核",
        )
        self.assertEqual(saved["status"], SamplingCheckIn.Status.OUTSIDE_CITY)
        self.assertEqual(saved["location_address"], "上海市徐汇区测试路1号")
        self.assertEqual(SamplingCheckIn.objects.count(), 3)
        geocode.assert_called_once()
        self.assertEqual(reverse_geocode_mock.call_count, 5)

    @patch("sampling.services.reports.reverse_geocode", return_value=ReverseGeocodeResult("安徽省六安市金安区测试路1号", "六安市"))
    @patch("sampling.services.reports.geocode_address", return_value=(116.5, 31.75))
    def test_city_only_delivery_address_allows_same_city_checkin(self, geocode, reverse_geocode_mock):
        self.task.delivery_address = "六安"
        self.task.save(update_fields=["delivery_address"])
        result = record_checkin(
            task_id=self.task.pk, batch_id=self.batch.pk, actor=self.sampler,
            latitude=31.75, longitude=116.5,
        )
        self.assertEqual(result["status"], SamplingCheckIn.Status.SAME_CITY)
        self.assertEqual(result["location_city"], "六安市")
        self.assertEqual(result["location_address"], "安徽省六安市金安区测试路1号")
        geocode.assert_called_once()
        self.assertEqual(reverse_geocode_mock.call_count, 2)
